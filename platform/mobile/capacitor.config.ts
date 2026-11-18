import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: process.env.BIOINTEL_APP_ID ?? 'com.biointel.workspace',
  appName: process.env.BIOINTEL_APP_NAME ?? 'BioIntel AI',
  webDir: 'dist',
  server: {
    androidScheme: 'https',
    iosScheme: 'capacitor',
    allowNavigation: [],
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 1200,
      backgroundColor: '#06111fff',
      showSpinner: false,
    },
    StatusBar: {
      style: 'LIGHT',
      backgroundColor: '#06111f',
    },
  },
};

export default config;
