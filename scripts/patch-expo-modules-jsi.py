#!/usr/bin/env python3
import os
import re
import sys

def patch_file(p, f, count):
    try:
        # 1. Package.swift
        if f == 'Package.swift':
            with open(p, 'r') as fp:
                c = fp.read()
            if 'ExpoModulesJSI' in c or 'expo-modules-jsi' in p:
                new_c = c
                if 'swift-tools-version' in new_c:
                    new_c = re.sub(r'// swift-tools-version:\s*6\.[1-9]\d*', '// swift-tools-version: 6.0', new_c)
                    new_c = re.sub(r'^(\s*)(\.enableUpcomingFeature\("(?:NonisolatedNonsendingByDefault|InferIsolatedConformances)"\),?)', r'\1// \2', new_c, flags=re.MULTILINE)
                new_c = new_c.replace('"-Werror", "ImplicitStrongCapture",', '')
                new_c = new_c.replace('"-Werror", "ImplicitStrongCapture"', '')
                if new_c != c:
                    os.chmod(p, 0o666)
                    with open(p, 'w') as fp:
                        fp.write(new_c)
                    count['pkg'] += 1
                    print('Patched Package.swift:', p)

        # 2. build-xcframework.sh
        elif f == 'build-xcframework.sh':
            with open(p, 'r') as fp:
                c = fp.read()
            if 'ExpoModulesJSI' in c or 'expo-modules-jsi' in p:
                if '-disableAutomaticPackageResolution' in c:
                    new_c = c.replace('-disableAutomaticPackageResolution \\\n', '').replace('-disableAutomaticPackageResolution', '')
                    os.chmod(p, 0o777)
                    with open(p, 'w') as fp:
                        fp.write(new_c)
                    count['sh'] += 1
                    print('Patched build-xcframework.sh:', p)

        # 3. Task+immediate.swift
        elif f == 'Task+immediate.swift':
            with open(p, 'r') as fp:
                c = fp.read()
            new_c = re.sub(
                r'if #available\(macOS 26\.0.*?}\s*else\s*{.*?}',
                'return Task(priority: priority ?? .high, operation: operation)',
                c,
                flags=re.DOTALL
            )
            if new_c != c:
                os.chmod(p, 0o666)
                with open(p, 'w') as fp:
                    fp.write(new_c)
                count['swift'] += 1
                print('Patched Task+immediate.swift:', p)

        # 4. JavaScriptRuntime.swift
        elif f == 'JavaScriptRuntime.swift':
            with open(p, 'r') as fp:
                c = fp.read()
            new_c = re.sub(
                r'for propertyName in propertyNames\s*\{\s*let propNameId = facebook\.jsi\.PropNameID\.forUtf8\(iRuntime,\s*std\.string\(propertyName\)\)\s*vector\.push_back\([^)]*\)\s*\}',
                'for propertyName in propertyNames {\n        expo.appendPropNameId(&vector, iRuntime, std.string(propertyName))\n      }',
                c
            )
            new_c = new_c.replace(
                'return expo.HostFunctionClosure(context, call, deallocate)',
                'return expo.createHostFunctionClosure(context, call, deallocate)'
            )
            new_c = re.sub(r'(?<!nonisolated\(unsafe\)\s)private weak (let|var)', 'nonisolated(unsafe) private weak var', new_c)
            new_c = re.sub(r'(?<!nonisolated\(unsafe\)\s)internal weak (let|var)', 'nonisolated(unsafe) internal weak var', new_c)
            if new_c != c:
                os.chmod(p, 0o666)
                with open(p, 'w') as fp:
                    fp.write(new_c)
                count['swift'] += 1
                print('Patched JavaScriptRuntime.swift:', p)

        # 5. Other Swift files (weak properties in Sendable classes)
        elif f.endswith('.swift') and ('expo-modules-jsi' in p or 'ExpoModulesJSI' in p):
            with open(p, 'r') as fp:
                c = fp.read()
            new_c = re.sub(r'(?<!nonisolated\(unsafe\)\s)private weak (let|var)', 'nonisolated(unsafe) private weak var', c)
            new_c = re.sub(r'(?<!nonisolated\(unsafe\)\s)internal weak (let|var)', 'nonisolated(unsafe) internal weak var', new_c)
            if new_c != c:
                os.chmod(p, 0o666)
                with open(p, 'w') as fp:
                    fp.write(new_c)
                count['swift'] += 1
                print('Patched weak property in:', p)

        # 6. RetainedSwiftPointer.h
        elif f == 'RetainedSwiftPointer.h':
            with open(p, 'r') as fp:
                c = fp.read()
            new_c = c.replace('using Deallocator = void(Context);', 'using Deallocator = void (*)(Context);')
            new_c = new_c.replace('Deallocator *_Nonnull _deallocator;', 'Deallocator _Nonnull _deallocator;')
            new_c = new_c.replace('std::move(deallocator)', 'deallocator')
            if new_c != c:
                os.chmod(p, 0o666)
                with open(p, 'w') as fp:
                    fp.write(new_c)
                count['h'] += 1
                print('Patched RetainedSwiftPointer.h:', p)

        # 7. HostFunctionClosure.h
        elif f == 'HostFunctionClosure.h':
            with open(p, 'r') as fp:
                c = fp.read()
            new_c = c.replace(
                'using Closure = bool(Context context, const facebook::jsi::Value *_Nonnull thisValue, const facebook::jsi::Value *_Nonnull args, size_t count, facebook::jsi::Value *_Nonnull result);',
                'using Closure = bool (*)(Context context, const facebook::jsi::Value *_Nonnull thisValue, const facebook::jsi::Value *_Nonnull args, size_t count, facebook::jsi::Value *_Nonnull result);'
            )
            new_c = new_c.replace('Closure *_Nonnull _closure;', 'Closure _Nonnull _closure;')
            if 'createHostFunctionClosure' not in new_c:
                factory_func = '''
inline HostFunctionClosure *_Nonnull createHostFunctionClosure(
    RetainedSwiftPointer::Context _Nonnull context,
    HostFunctionClosure::Closure _Nonnull closure,
    RetainedSwiftPointer::Deallocator _Nonnull deallocator) {
  return new HostFunctionClosure(context, closure, deallocator);
}

} // namespace expo
'''
                new_c = re.sub(r'\}\s*//\s*namespace\s*expo\s*$', factory_func, new_c)
            if new_c != c:
                os.chmod(p, 0o666)
                with open(p, 'w') as fp:
                    fp.write(new_c)
                count['h'] += 1
                print('Patched HostFunctionClosure.h:', p)

        # 8. HostObjectCallbacks.h
        elif f == 'HostObjectCallbacks.h':
            with open(p, 'r') as fp:
                c = fp.read()
            if 'appendPropNameId' not in c:
                helper = '''
inline void appendPropNameId(HostObjectCallbacks::PropNameIds &vector, facebook::jsi::IRuntime &runtime, const std::string &name) {
  vector.push_back(facebook::jsi::PropNameID::forUtf8(runtime, name));
}

} // namespace expo
'''
                new_c = re.sub(r'\}\s*//\s*namespace\s*expo', helper, c)
                if new_c != c:
                    os.chmod(p, 0o666)
                    with open(p, 'w') as fp:
                        fp.write(new_c)
                    count['h'] += 1
                    print('Patched HostObjectCallbacks.h:', p)

        # 9. PlaybackCoordinator.swift (react-native-jet-video)
        elif f == 'PlaybackCoordinator.swift':
            with open(p, 'r') as fp:
                c = fp.read()
            old_patterns = [
                'if abs(track.fraction - fraction) > 0.01 {',
                'let diff: Double = abs(track.fraction - fraction)\n      if diff > 0.01 {'
            ]
            new_code = 'if Swift.abs(track.fraction - fraction) > 0.01 {'
            new_c = c
            for op in old_patterns:
                if op in new_c:
                    new_c = new_c.replace(op, new_code)
            if new_c != c:
                os.chmod(p, 0o666)
                with open(p, 'w') as fp:
                    fp.write(new_c)
                count['swift'] += 1
                print('Patched PlaybackCoordinator.swift:', p)

    except Exception as e:
        print('Error patching', p, e)

def patch_expo_modules_jsi(search_root):
    count = {'pkg': 0, 'sh': 0, 'swift': 0, 'h': 0}
    if not os.path.exists(search_root):
        return count

    target_files = {
        'Package.swift', 'build-xcframework.sh', 'Task+immediate.swift',
        'JavaScriptRuntime.swift', 'RetainedSwiftPointer.h',
        'HostFunctionClosure.h', 'HostObjectCallbacks.h',
        'PlaybackCoordinator.swift'
    }

    for root, dirs, files in os.walk(search_root, followlinks=True):
        for f in files:
            if f in target_files or f.endswith('.swift'):
                p = os.path.join(root, f)
                patch_file(p, f, count)

    return count

def main():
    search_dirs = sys.argv[1:] if len(sys.argv) > 1 else ['.', os.path.expanduser('~/.bun')]
    total = {'pkg': 0, 'sh': 0, 'swift': 0, 'h': 0}
    for d in search_dirs:
        res = patch_expo_modules_jsi(os.path.abspath(os.path.expanduser(d)))
        for k in total:
            total[k] += res[k]
    print(f'Done patching expo-modules-jsi: {total}')

if __name__ == '__main__':
    main()
