// Kollektivgedächtnis — Foto-App für die Station (Weg A).
//
// Baut ein unsigniertes-per-Debug-Key signiertes APK, das per Seitenladen aufs
// Handy kommt: kein Play-Konto, kein Store, keine Signaturkette zu pflegen.
// Debug-Signatur ist hier bewusst die richtige Wahl -- ein Release-Keystore
// müsste sicher verwahrt werden und kauft für eine zweitägige Ausstellung
// nichts, ausser der Verpflichtung, ihn nicht zu verlieren.
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "art.artesmobiles.kg"
    compileSdk = 34

    defaultConfig {
        applicationId = "art.artesmobiles.kg"
        // 26 (Android 8) statt 21: darunter fehlt CameraX ohnehin die
        // Grundlage, und ein Handy älter als 2017 steht am Booth nicht.
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // Mit dem Debug-Key signiert, damit `assembleRelease` ein direkt
            // installierbares APK liefert statt eines unsignierten, das
            // Android verweigert.
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { viewBinding = false }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.activity:activity-ktx:1.9.2")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")

    val camerax = "1.3.4"
    implementation("androidx.camera:camera-core:$camerax")
    implementation("androidx.camera:camera-camera2:$camerax")
    implementation("androidx.camera:camera-lifecycle:$camerax")
    implementation("androidx.camera:camera-view:$camerax")

    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:4.12.2")
    testImplementation("androidx.test:core:1.6.1")
}
