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

        # 10. GalleryToolbar.swift (react-native-jet-gallery)
        elif f == 'GalleryToolbar.swift':
            with open(p, 'r') as fp:
                c = fp.read()
            old_glass = '''  private func glass(_ content: UIView) -> UIView {
    guard #available(iOS 26, *) else { return content }

    let effect = UIGlassEffect(style: .regular)
    effect.isInteractive = true

    let effectView = UIVisualEffectView(effect: effect)
    effectView.cornerConfiguration = .capsule()
    effectView.translatesAutoresizingMaskIntoConstraints = false
    effectView.contentView.addSubview(content)

    NSLayoutConstraint.activate([
      content.topAnchor.constraint(equalTo: effectView.contentView.topAnchor),
      content.bottomAnchor.constraint(equalTo: effectView.contentView.bottomAnchor),
      content.leadingAnchor.constraint(equalTo: effectView.contentView.leadingAnchor),
      content.trailingAnchor.constraint(equalTo: effectView.contentView.trailingAnchor),
    ])

    return effectView
  }'''
            new_glass = '''  private func glass(_ content: UIView) -> UIView {
    return content
  }'''
            if old_glass in c:
                new_c = c.replace(old_glass, new_glass)
                os.chmod(p, 0o666)
                with open(p, 'w') as fp:
                    fp.write(new_c)
                count['swift'] += 1
                print('Patched GalleryToolbar.swift:', p)

        # 11. GalleryViewController.swift (react-native-jet-gallery)
        elif f == 'GalleryViewController.swift':
            with open(p, 'r') as fp:
                c = fp.read()
            old_guide = '''    let topGuide: UILayoutGuide
    if #available(iOS 26, *) {
      topGuide = view.layoutGuide(for: .safeArea(cornerAdaptation: .vertical))
    } else {
      topGuide = view.safeAreaLayoutGuide
    }'''
            new_guide = '    let topGuide: UILayoutGuide = view.safeAreaLayoutGuide'
            if old_guide in c:
                new_c = c.replace(old_guide, new_guide)
                os.chmod(p, 0o666)
                with open(p, 'w') as fp:
                    fp.write(new_c)
                count['swift'] += 1
                print('Patched GalleryViewController.swift:', p)

        # 12. *.swiftinterface (ExpoModulesCore / Swift 6.1 compatibility)
        elif f.endswith('.swiftinterface'):
            with open(p, 'r', encoding='utf-8', errors='replace') as fp:
                c = fp.read()
            changed = False
            if ': @_Concurrency.MainActor ' in c:
                c = c.replace(': @_Concurrency.MainActor ', ': ')
                changed = True
            if '// swift-compiler-version: Apple Swift version 6.3' in c:
                c = c.replace('// swift-compiler-version: Apple Swift version 6.3', '// swift-compiler-version: Apple Swift version 6.1')
                changed = True
            if changed:
                os.chmod(p, 0o666)
                with open(p, 'w', encoding='utf-8') as fp:
                    fp.write(c)
                count['swiftinterface'] = count.get('swiftinterface', 0) + 1
                print('Patched swiftinterface:', p)

        # 13. Expo tarballs (.tar.gz) containing xcframeworks
        elif f.endswith('.tar.gz') and 'Expo' in f:
            import tarfile, io
            try:
                with tarfile.open(p, 'r:gz') as tar:
                    members = tar.getmembers()
                    needs_patch = False
                    for m in members:
                        if m.name.endswith('.swiftinterface'):
                            extracted = tar.extractfile(m)
                            if extracted:
                                text = extracted.read().decode('utf-8', errors='replace')
                                if ': @_Concurrency.MainActor ' in text:
                                    needs_patch = True
                                    break
                    if needs_patch:
                        new_tar_io = io.BytesIO()
                        with tarfile.open(fileobj=new_tar_io, mode='w:gz') as new_tar:
                            for m in members:
                                extracted = tar.extractfile(m)
                                if extracted and m.name.endswith('.swiftinterface'):
                                    text = extracted.read().decode('utf-8', errors='replace')
                                    if ': @_Concurrency.MainActor ' in text:
                                        text = text.replace(': @_Concurrency.MainActor ', ': ')
                                        text = text.replace('// swift-compiler-version: Apple Swift version 6.3', '// swift-compiler-version: Apple Swift version 6.1')
                                        data = text.encode('utf-8')
                                        m.size = len(data)
                                        new_tar.addfile(m, io.BytesIO(data))
                                    else:
                                        new_tar.addfile(m, io.BytesIO(text.encode('utf-8')))
                                elif extracted:
                                    new_tar.addfile(m, extracted)
                                else:
                                    new_tar.addfile(m)
                        os.chmod(p, 0o666)
                        with open(p, 'wb') as out_f:
                            out_f.write(new_tar_io.getvalue())
                        count['tar'] = count.get('tar', 0) + 1
                        print('Patched in-tar swiftinterfaces in:', p)
            except Exception as e:
                print('Error patching tarball', p, e)

        # 14. TranslationHelpers.swift (expo-translate-text / iOS 18 compatibility)
        elif f == 'TranslationHelpers.swift':
            with open(p, 'r') as fp:
                c = fp.read()
            old_code = '''  if #available(iOS 26.4, *), let preferredStrategy {
    return TranslationSession.Configuration(
      source: source,
      target: target,
      preferredStrategy: makePreferredStrategy(preferredStrategy)
    )
  }

  return TranslationSession.Configuration(source: source, target: target)'''
            new_code = '  return TranslationSession.Configuration(source: source, target: target)'

            old_func = '''@available(iOS 26.4, *)
private func makePreferredStrategy(_ preferredStrategy: String) -> TranslationSession.Strategy {
  switch preferredStrategy {
  case "highFidelity":
    return .highFidelity
  default:
    return .lowLatency
  }
}'''
            changed = False
            if old_code in c:
                c = c.replace(old_code, new_code)
                changed = True
            if old_func in c:
                c = c.replace(old_func, '')
                changed = True
            if changed:
                os.chmod(p, 0o666)
                with open(p, 'w') as fp:
                    fp.write(c)
                count['swift'] += 1
                print('Patched TranslationHelpers.swift:', p)

        # 15. RouterToolbarHostView.swift (expo-router)
        elif f == 'RouterToolbarHostView.swift':
            with open(p, 'r') as fp:
                c = fp.read()
            new_c = re.sub(
                r'if #available\(iOS 26\.0, \*\) \{\s*if let hidesSharedBackground = menu\.hidesSharedBackground \{.*?\}\s*\}',
                '',
                c,
                flags=re.DOTALL
            )
            if new_c != c:
                os.chmod(p, 0o666)
                with open(p, 'w') as fp:
                    fp.write(new_c)
                count['swift'] += 1
                print('Patched RouterToolbarHostView.swift:', p)

        # 16. RouterToolbarItemView.swift (expo-router)
        elif f == 'RouterToolbarItemView.swift':
            with open(p, 'r') as fp:
                c = fp.read()
            old_search = '''    } else if type == .searchBar {
      guard #available(iOS 26.0, *), let controller = self.host?.findViewController() else {
        // Check for iOS 26, should already be guarded by the JS side, so this warning will only fire if controller is nil
        logger?.warn(
          "[expo-router] navigationItem.searchBarPlacementBarButtonItem not available. This is most likely a bug in expo-router."
        )
        currentBarButtonItem = nil
        return
      }
      guard let navController = controller.navigationController else {
        currentBarButtonItem = nil
        return
      }
      guard navController.isNavigationBarHidden == false else {
        logger?.warn(
          "[expo-router] Toolbar.SearchBarPreferredSlot should only be used when stack header is shown."
        )
        currentBarButtonItem = nil
        return
      }

      item = controller.navigationItem.searchBarPlacementBarButtonItem'''

            new_search = '''    } else if type == .searchBar {
      currentBarButtonItem = nil
      return'''

            new_c = c.replace(old_search, new_search) if old_search in c else c
            new_c = re.sub(
                r'if #available\(iOS 26\.0, \*\) \{\s*item\.hidesSharedBackground = hidesSharedBackground\s*item\.sharesBackground = sharesBackground\s*\}',
                '',
                new_c
            )
            new_c = re.sub(
                r'if #available\(iOS 26\.0, \*\) \{\s*if let badgeConfig = badgeConfiguration \{.*?\}\s*else\s*\{\s*item\.badge = nil\s*\}\s*\}',
                '',
                new_c,
                flags=re.DOTALL
            )
            if new_c != c:
                os.chmod(p, 0o666)
                with open(p, 'w') as fp:
                    fp.write(new_c)
                count['swift'] += 1
                print('Patched RouterToolbarItemView.swift:', p)

        # 17. RouterToolbarModule.swift (expo-router)
        elif f == 'RouterToolbarModule.swift':
            with open(p, 'r') as fp:
                c = fp.read()
            old_prominent = '''    case .prominent:
      if #available(iOS 26.0, *) {
        return .prominent
      } else {
        return .done
      }'''
            new_prominent = '''    case .prominent:
      return .done'''
            if old_prominent in c:
                new_c = c.replace(old_prominent, new_prominent)
                os.chmod(p, 0o666)
                with open(p, 'w') as fp:
                    fp.write(new_c)
                count['swift'] += 1
                print('Patched RouterToolbarModule.swift:', p)

        # 18. MediaHandler.swift (expo-image-picker / iOS 18 compatibility)
        elif f == 'MediaHandler.swift':
            with open(p, 'r') as fp:
                c = fp.read()
            old_asset = '''  private func getMimeType(from asset: PHAsset?, fileExtension: String) -> String? {
    let utType: UTType? = if #available(iOS 26.0, *) {
      asset?.contentType ?? UTType(filenameExtension: fileExtension)
    } else {
      UTType(filenameExtension: fileExtension)
    }
    return utType?.preferredMIMEType
  }'''
            new_asset = '''  private func getMimeType(from asset: PHAsset?, fileExtension: String) -> String? {
    let utType: UTType? = UTType(filenameExtension: fileExtension)
    return utType?.preferredMIMEType
  }'''

            old_resource = '''  private func getMimeType(from resource: PHAssetResource, fileExtension: String) -> String? {
    let utType: UTType? = if #available(iOS 26.0, *) {
      resource.contentType
    } else {
      UTType(resource.uniformTypeIdentifier) ?? UTType(filenameExtension: fileExtension)
    }
    return utType?.preferredMIMEType
  }'''
            new_resource = '''  private func getMimeType(from resource: PHAssetResource, fileExtension: String) -> String? {
    let utType: UTType? = UTType(resource.uniformTypeIdentifier) ?? UTType(filenameExtension: fileExtension)
    return utType?.preferredMIMEType
  }'''

            changed = False
            if old_asset in c:
                c = c.replace(old_asset, new_asset)
                changed = True
            if old_resource in c:
                c = c.replace(old_resource, new_resource)
                changed = True
            if changed:
                os.chmod(p, 0o666)
                with open(p, 'w') as fp:
                    fp.write(c)
                count['swift'] += 1
                print('Patched MediaHandler.swift:', p)

    except Exception as e:
        print('Error patching', p, e)

def patch_expo_modules_jsi(search_root):
    count = {'pkg': 0, 'sh': 0, 'swift': 0, 'h': 0, 'swiftinterface': 0, 'tar': 0}
    if not os.path.exists(search_root):
        return count

    target_files = {
        'Package.swift', 'build-xcframework.sh', 'Task+immediate.swift',
        'JavaScriptRuntime.swift', 'RetainedSwiftPointer.h',
        'HostFunctionClosure.h', 'HostObjectCallbacks.h',
        'PlaybackCoordinator.swift', 'GalleryToolbar.swift',
        'GalleryViewController.swift', 'TranslationHelpers.swift',
        'RouterToolbarHostView.swift', 'RouterToolbarItemView.swift',
        'RouterToolbarModule.swift', 'MediaHandler.swift'
    }

    for root, dirs, files in os.walk(search_root, followlinks=True):
        for f in files:
            if f in target_files or f.endswith('.swift') or f.endswith('.swiftinterface') or (f.endswith('.tar.gz') and 'Expo' in f):
                p = os.path.join(root, f)
                patch_file(p, f, count)

    return count

def main():
    search_dirs = sys.argv[1:] if len(sys.argv) > 1 else ['.', os.path.expanduser('~/.bun')]
    total = {'pkg': 0, 'sh': 0, 'swift': 0, 'h': 0, 'swiftinterface': 0, 'tar': 0}
    for d in search_dirs:
        res = patch_expo_modules_jsi(os.path.abspath(os.path.expanduser(d)))
        for k in total:
            total[k] += res.get(k, 0)
    print(f'Done patching expo-modules-jsi: {total}')

if __name__ == '__main__':
    main()
