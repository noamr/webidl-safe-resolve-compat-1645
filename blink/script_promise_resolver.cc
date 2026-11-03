// Copyright 2014 The Chromium Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "third_party/blink/renderer/bindings/core/v8/script_promise_resolver.h"

#include "base/feature_list.h"
#include "base/logging.h"
#include "third_party/blink/public/platform/task_type.h"
#include "third_party/blink/renderer/bindings/core/v8/capture_source_location.h"
#include "third_party/blink/renderer/bindings/core/v8/v8_binding_for_core.h"
#include "third_party/blink/renderer/bindings/core/v8/v8_microtasks_scope.h"
#include "third_party/blink/renderer/bindings/core/v8/v8_throw_dom_exception.h"
#include "third_party/blink/renderer/core/execution_context/execution_context.h"
#include "third_party/blink/renderer/core/probe/core_probes.h"
#include "third_party/blink/renderer/platform/bindings/lazy_source_location.h"
#include "third_party/blink/renderer/platform/bindings/source_location.h"
#include "third_party/blink/renderer/platform/bindings/v8_throw_exception.h"
#include "third_party/blink/renderer/platform/runtime_enabled_features.h"
#include "third_party/blink/renderer/platform/wtf/functional.h"

#if DCHECK_IS_ON()
#include "base/debug/alias.h"
#include "components/crash/core/common/crash_key.h"
#endif

namespace blink {

// ---- Instrumentation for whatwg/webidl#1645 (SafePromiseResolve) ----
// Not for landing. Inserted into script_promise_resolver.cc.

BASE_FEATURE(kEmulateSafePromiseResolve, base::FEATURE_DISABLED_BY_DEFAULT);

namespace {

enum class SafeResolveKind {
  kNotObject,
  kNoThen,
  kNonCallableDataThen,
  kDataThenable,
  kAccessorThen,
  kProxy,
  kInterceptor,
  kModuleNamespace,
  kLookupThrew,
};

const char* SafeResolveKindName(SafeResolveKind kind) {
  switch (kind) {
    case SafeResolveKind::kNotObject:
      return "not-object";
    case SafeResolveKind::kNoThen:
      return "no-then";
    case SafeResolveKind::kNonCallableDataThen:
      return "noncallable-data-then";
    case SafeResolveKind::kDataThenable:
      return "data-thenable";
    case SafeResolveKind::kAccessorThen:
      return "accessor-then";
    case SafeResolveKind::kProxy:
      return "proxy";
    case SafeResolveKind::kInterceptor:
      return "interceptor";
    case SafeResolveKind::kModuleNamespace:
      return "module-namespace";
    case SafeResolveKind::kLookupThrew:
      return "lookup-threw";
  }
}

// Whether SafePromiseResolve would defer in a way that is observable: the
// `then` lookup could run user code (RequiresDeferredPromiseResolution steps 2,
// per PropertyAccessCouldRunUserCode, with legacy platform objects treated as
// impure per the PR). Data thenables are deferred too, but `then` is still
// called in the same microtask, so they're reported separately.
bool IsObservable(SafeResolveKind kind) {
  return kind == SafeResolveKind::kAccessorThen ||
         kind == SafeResolveKind::kProxy ||
         kind == SafeResolveKind::kInterceptor;
  // Module namespaces are excluded: in practice they reach here only from
  // dynamic import(), which ECMA-262 resolves, not Web IDL.
}

// Classifies `value` without running user code. `holder_ctor` is set to the
// constructor name of the object on the prototype chain that decided it.
SafeResolveKind ClassifyForSafeResolve(v8::Isolate* isolate,
                                       v8::Local<v8::Context> context,
                                       v8::Local<v8::Value> value,
                                       String& holder_ctor,
                                       int& depth) {
  if (!value->IsObject()) {
    return SafeResolveKind::kNotObject;
  }
  v8::TryCatch try_catch(isolate);
  v8::Local<v8::String> then_key = V8AtomicString(isolate, "then");
  v8::Local<v8::Value> current = value;
  depth = 0;
  while (current->IsObject()) {
    v8::Local<v8::Object> object = current.As<v8::Object>();
    if (object->IsProxy()) {
      holder_ctor = "Proxy";
      return SafeResolveKind::kProxy;
    }
    if (object->IsModuleNamespaceObject()) {
      holder_ctor = "Module";
      return SafeResolveKind::kModuleNamespace;
    }
    holder_ctor = ToCoreStringWithUndefinedOrNullCheck(
        isolate, object->GetConstructorName());
    if (object->HasNamedLookupInterceptor() ||
        object->HasIndexedLookupInterceptor()) {
      return SafeResolveKind::kInterceptor;
    }
    v8::Local<v8::Value> descriptor;
    if (!object->GetOwnPropertyDescriptor(context, then_key)
             .ToLocal(&descriptor)) {
      return SafeResolveKind::kLookupThrew;
    }
    if (descriptor->IsObject()) {
      v8::Local<v8::Object> desc = descriptor.As<v8::Object>();
      v8::Local<v8::Value> getter;
      if (desc->HasOwnProperty(context, V8AtomicString(isolate, "get"))
              .FromMaybe(false)) {
        if (desc->Get(context, V8AtomicString(isolate, "get"))
                .ToLocal(&getter) &&
            !getter->IsUndefined()) {
          return SafeResolveKind::kAccessorThen;
        }
        // Setter-only accessor: [[Get]] returns undefined.
        return SafeResolveKind::kNoThen;
      }
      v8::Local<v8::Value> then_value;
      if (desc->Get(context, V8AtomicString(isolate, "value"))
              .ToLocal(&then_value) &&
          then_value->IsFunction()) {
        return SafeResolveKind::kDataThenable;
      }
      return SafeResolveKind::kNonCallableDataThen;
    }
    current = object->GetPrototype();
    ++depth;
  }
  return SafeResolveKind::kNoThen;
}

// Deferred steps of SafePromiseResolve: PerformPromiseResolution(promise,
// resolution, ~deferred~), approximated with the wrapper's resolving
// functions. In the non-callable case, `resolve(value)` looks `then` up again,
// so a getter runs twice there.
void DeferredThen(const v8::FunctionCallbackInfo<v8::Value>& info) {
  v8::Isolate* isolate = info.GetIsolate();
  v8::Local<v8::Context> context = isolate->GetCurrentContext();
  v8::Local<v8::Value> value = info.DataV2().As<v8::Value>();
  v8::Local<v8::Value> resolve = info[0];
  v8::Local<v8::Value> reject = info[1];
  if (!resolve->IsFunction() || !reject->IsFunction()) {
    return;
  }
  v8::TryCatch try_catch(isolate);
  v8::Local<v8::Value> then;
  if (!value.As<v8::Object>()->Get(context, V8AtomicString(isolate, "then"))
           .ToLocal(&then)) {
    v8::Local<v8::Value> exception = try_catch.Exception();
    try_catch.Reset();
    std::ignore = reject.As<v8::Function>()->Call(
        context, v8::Undefined(isolate), 1, &exception);
    return;
  }
  if (then->IsFunction()) {
    v8::Local<v8::Value> args[] = {resolve, reject};
    if (then.As<v8::Function>()->Call(context, value, 2, args).IsEmpty()) {
      v8::Local<v8::Value> exception = try_catch.Exception();
      try_catch.Reset();
      std::ignore = reject.As<v8::Function>()->Call(
          context, v8::Undefined(isolate), 1, &exception);
    }
    return;
  }
  std::ignore =
      resolve.As<v8::Function>()->Call(context, v8::Undefined(isolate), 1,
                                       &value);
}

}  // namespace

v8::Local<v8::Value> ProbeSafePromiseResolve(ScriptState* script_state,
                                             v8::Local<v8::Value> value,
                                             const char* site,
                                             const char* api) {
  v8::Isolate* isolate = script_state->GetIsolate();
  v8::Local<v8::Context> context = script_state->GetContext();
  String holder_ctor;
  int depth = 0;
  SafeResolveKind kind =
      ClassifyForSafeResolve(isolate, context, value, holder_ctor, depth);
  if (kind == SafeResolveKind::kNotObject ||
      kind == SafeResolveKind::kNoThen ||
      kind == SafeResolveKind::kNonCallableDataThen) {
    return value;
  }
  ExecutionContext* execution_context = ExecutionContext::From(script_state);
  String value_ctor = ToCoreStringWithUndefinedOrNullCheck(
      isolate, value.As<v8::Object>()->GetConstructorName());
  LOG(ERROR) << "SAFE_RESOLVE kind=" << SafeResolveKindName(kind)
             << " site=" << site << " api=" << (api ? api : "")
             << " value_ctor=" << value_ctor.Utf8() << " holder_ctor=" << holder_ctor.Utf8()
             << " depth=" << depth << " doc="
             << (execution_context ? execution_context->Url().GetString().Utf8()
                                   : std::string())
             << " script=" << CaptureCurrentScriptUrl(isolate).Utf8()
             << " emulate="
             << base::FeatureList::IsEnabled(kEmulateSafePromiseResolve);
  if (!IsObservable(kind) ||
      !base::FeatureList::IsEnabled(kEmulateSafePromiseResolve)) {
    return value;
  }
  v8::Local<v8::Function> deferred_then;
  if (!v8::Function::New(context, DeferredThen, value, 2)
           .ToLocal(&deferred_then)) {
    return value;
  }
  v8::Local<v8::Object> wrapper = v8::Object::New(isolate);
  std::ignore = wrapper->SetPrototype(context, v8::Null(isolate));
  std::ignore = wrapper->CreateDataProperty(
      context, V8AtomicString(isolate, "then"), deferred_then);
  return wrapper;
}
// ---- End instrumentation ----


ScriptPromiseResolverBase::ScriptPromiseResolverBase(
    ScriptState* script_state,
    const ExceptionContext& exception_context)
    : state_(kPending),
      script_state_(script_state),
      exception_context_(exception_context) {
  // A call pro Promise::Resolver::New() would reset a pending
  // excepiton, so make sure we don't get here with one.
  v8::Isolate* isolate = script_state->GetIsolate();
  ExceptionState::AssertNoPendingException(isolate);
  resolver_.Reset(
      isolate,
      v8::Promise::Resolver::New(script_state->GetContext()).ToLocalChecked());
  if (RuntimeEnabledFeatures::LongAnimationFrameSourceCharPositionEnabled()) {
    lazy_source_location_ = LazySourceLocation::FromCurrentStack(isolate);
  } else {
    lazy_source_location_ = MakeGarbageCollected<LazySourceLocation>(
        CaptureCurrentScriptUrl(isolate));
  }
}

ScriptPromiseResolverBase::~ScriptPromiseResolverBase() = default;

#if DCHECK_IS_ON()
void ScriptPromiseResolverBase::Dispose() {
  // This assertion fails if:
  //  - promise() is called at least once and
  //  - this resolver is destructed before it is resolved, rejected,
  //    detached, the V8 isolate is terminated or the associated
  //    ExecutionContext is stopped.
  const bool is_properly_detached = state_ == kDone || !is_promise_called_ ||
                                    !GetScriptState()->ContextIsValid() ||
                                    !GetExecutionContext() ||
                                    GetExecutionContext()->IsContextDestroyed();
  if (!is_properly_detached && !suppress_detach_check_) {
    // This is here to make it easier to track down which promise resolvers are
    // being abandoned. See https://crbug.com/873980.
    static crash_reporter::CrashKeyString<1024> trace_key(
        "scriptpromiseresolver-trace");
    crash_reporter::SetCrashKeyStringToStackTrace(&trace_key,
                                                  create_stack_trace_);
    DCHECK(false)
        << "ScriptPromiseResolverBase was not properly detached; created at\n"
        << create_stack_trace_.ToString();
  }
}
#endif

void ScriptPromiseResolverBase::Reject(DOMException* value) {
  Reject<DOMException>(value);
}

void ScriptPromiseResolverBase::Reject(v8::Local<v8::Value> value) {
  Reject<IDLAny>(value);
}

void ScriptPromiseResolverBase::Reject(const ScriptValue& value) {
  Reject<IDLAny>(value);
}

void ScriptPromiseResolverBase::Reject(const char* value) {
  Reject<IDLString>(value);
}

void ScriptPromiseResolverBase::Reject(bool value) {
  Reject<IDLBoolean>(value);
}

void ScriptPromiseResolverBase::RejectWithDOMException(
    DOMExceptionCode exception_code,
    const String& message) {
  ScriptState::Scope scope(script_state_.Get());
  v8::Isolate* isolate = script_state_->GetIsolate();
  auto exception =
      V8ThrowDOMException::CreateOrDie(isolate, exception_code, message);
  ApplyContextToException(
      script_state_, exception, exception_context_.GetType(),
      exception_context_.GetClassName(), exception_context_.GetPropertyName());
  Reject(exception);
}

void ScriptPromiseResolverBase::RejectWithSecurityError(
    const String& sanitized_message,
    const String& unsanitized_message) {
  ScriptState::Scope scope(script_state_.Get());
  v8::Isolate* isolate = script_state_->GetIsolate();
  auto exception = V8ThrowDOMException::CreateOrDie(
      isolate, DOMExceptionCode::kSecurityError, sanitized_message,
      unsanitized_message);
  ApplyContextToException(
      script_state_, exception, exception_context_.GetType(),
      exception_context_.GetClassName(), exception_context_.GetPropertyName());
  Reject(exception);
}

String AddContext(const ExceptionContext& context, const String& message) {
  return ExceptionMessages::AddContextToMessage(
      context.GetType(), context.GetClassName(), context.GetPropertyName(),
      message);
}

void ScriptPromiseResolverBase::RejectWithTypeError(const String& message) {
  ScriptState::Scope scope(script_state_.Get());
  Reject(V8ThrowException::CreateTypeError(
      script_state_->GetIsolate(), AddContext(exception_context_, message)));
}

void ScriptPromiseResolverBase::RejectWithRangeError(const String& message) {
  ScriptState::Scope scope(script_state_.Get());
  Reject(V8ThrowException::CreateRangeError(
      script_state_->GetIsolate(), AddContext(exception_context_, message)));
}

void ScriptPromiseResolverBase::Detach() {
  // Reset state even if we're already kDone. The resolver_ will not have been
  // reset yet if this was marked kDone due to resolve/reject, and an explicit
  // Detach() should really clear everything.
  state_ = kDone;
  resolver_.Reset();
  value_.Reset();
}

void ScriptPromiseResolverBase::NotifyResolveOrReject() {
  if (GetExecutionContext()->IsContextPaused()) {
    ScheduleResolveOrReject();
    return;
  }
  // TODO(esprehn): This is a hack, instead we should CHECK that
  // script is allowed, and v8 should be running the entry hooks below and
  // crashing if script is forbidden. We should then audit all users of
  // ScriptPromiseResolverBase and the related specs and switch to an async
  // resolve.
  // See: http://crbug.com/663476
  if (ScriptForbiddenScope::IsScriptForbidden()) {
    ScheduleResolveOrReject();
    return;
  }
  ResolveOrRejectImmediately();
}

void ScriptPromiseResolverBase::ResolveOrRejectImmediately() {
  DCHECK(!GetExecutionContext()->IsContextDestroyed());
  DCHECK(!GetExecutionContext()->IsContextPaused());

  probe::WillHandlePromise(
      GetExecutionContext(), script_state_, state_ == kResolving,
      exception_context_.GetClassName(), exception_context_.GetPropertyName(),
      lazy_source_location_.Get());

  V8DoNotRunMicrotasksScope microtasks_scope(script_state_);
  auto resolver = resolver_.Get(script_state_->GetIsolate());
  if (state_ == kResolving) {
    // TODO(462010740): clean up call sites with pending exceptions.
    ExceptionState::AssertNoPendingException(script_state_->GetIsolate());
    std::ignore = resolver->Resolve(
        script_state_->GetContext(),
        ProbeSafePromiseResolve(
            script_state_, value_.Get(script_state_->GetIsolate()), "resolver",
            exception_context_.GetClassName()));
  } else {
    DCHECK_EQ(state_, kRejecting);
    std::ignore = resolver->Reject(script_state_->GetContext(),
                                   value_.Get(script_state_->GetIsolate()));
  }

  // Don't reset `resolver_`, so that Promise() still works.
  state_ = kDone;
  value_.Reset();
}

void ScriptPromiseResolverBase::ScheduleResolveOrReject() {
  GetExecutionContext()
      ->GetTaskRunner(TaskType::kMicrotask)
      ->PostTask(FROM_HERE,
                 BindOnce(&ScriptPromiseResolverBase::ResolveOrRejectDeferred,
                          WrapPersistent(this)));
}

void ScriptPromiseResolverBase::ResolveOrRejectDeferred() {
  DCHECK(state_ == kResolving || state_ == kRejecting);
  if (!GetExecutionContext()) {
    return;
  }

  ScriptState::Scope scope(script_state_.Get());
  ResolveOrRejectImmediately();
}

void ScriptPromiseResolverBase::Trace(Visitor* visitor) const {
  visitor->Trace(script_state_);
  visitor->Trace(resolver_);
  visitor->Trace(value_);
  visitor->Trace(lazy_source_location_);
}

ExecutionContext* ScriptPromiseResolverBase::GetExecutionContext() {
  if (!GetScriptState()->ContextIsValid()) {
    return nullptr;
  }
  auto* execution_context = ExecutionContext::From(script_state_);
  return execution_context->IsContextDestroyed() ? nullptr : execution_context;
}

}  // namespace blink
