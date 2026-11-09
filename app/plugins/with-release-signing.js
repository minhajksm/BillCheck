// Signs release builds with FairCare's own upload key instead of the shared
// debug key the Expo template uses, which Google Play rejects.
//
// android/ is generated (`npx expo prebuild --clean` deletes and rewrites
// it), so the change is made here rather than in android/app/build.gradle.
// The key and its passwords live in app/credentials/, which is gitignored:
//
//   app/credentials/upload.keystore
//   app/credentials/upload-keystore.properties
//     storeFile=upload.keystore
//     storePassword=...
//     keyAlias=upload
//     keyPassword=...
//
// Without that file, release builds fall back to the debug key, so a local
// release build still works for testing on a phone. Play refuses those.
const { withAppBuildGradle } = require('expo/config-plugins');

const MARKER = '// FairCare release signing';

const LOAD = `${MARKER}: app/credentials/upload-keystore.properties, gitignored.
def faircareSigningFile = rootProject.file('../credentials/upload-keystore.properties')
def faircareSigning = new Properties()
if (faircareSigningFile.exists()) {
    faircareSigningFile.withInputStream { faircareSigning.load(it) }
}

android {`;

const CONFIG = `signingConfigs {
        release {
            if (faircareSigningFile.exists()) {
                storeFile new File(faircareSigningFile.parentFile, faircareSigning['storeFile'])
                storePassword faircareSigning['storePassword']
                keyAlias faircareSigning['keyAlias']
                keyPassword faircareSigning['keyPassword']
            }
        }`;

const DEBUG_SIGNED_RELEASE = /(release \{\s*\n(?:\s*\/\/[^\n]*\n)*\s*)signingConfig signingConfigs\.debug/;

function withReleaseSigning(config) {
  return withAppBuildGradle(config, (config) => {
    let gradle = config.modResults.contents;
    if (gradle.includes(MARKER)) return config;

    const steps = [
      [/^android \{/m, LOAD],
      [/signingConfigs \{/, CONFIG],
      [
        DEBUG_SIGNED_RELEASE,
        '$1signingConfig faircareSigningFile.exists() ? signingConfigs.release : signingConfigs.debug',
      ],
    ];
    for (const [pattern, replacement] of steps) {
      if (!pattern.test(gradle)) {
        throw new Error(
          `with-release-signing: android/app/build.gradle no longer matches ${pattern}. ` +
            'The Expo template changed; update plugins/with-release-signing.js.',
        );
      }
      gradle = gradle.replace(pattern, replacement);
    }
    config.modResults.contents = gradle;
    return config;
  });
}

module.exports = withReleaseSigning;
