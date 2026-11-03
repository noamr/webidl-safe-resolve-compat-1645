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
         kind == SafeResolveKind::kInterceptor ||
         kind == SafeResolveKind::kModuleNamespace;
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
