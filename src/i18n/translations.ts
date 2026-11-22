import type { AppLang, NavSection } from '../types';

export interface Translations {
  appName: string;
  nav: Record<NavSection, string>;
  common: {
    search: string;
    filter: string;
    reset: string;
    save: string;
    cancel: string;
    close: string;
    refresh: string;
    loading: string;
    noData: string;
    actions: string;
    all: string;
    yes: string;
    no: string;
    download: string;
    wilaya: string;
    commune: string;
    status: string;
    source: string;
    confidence: string;
  };
  statuses: {
    VERIFIED: string;
    UNVERIFIED: string;
    NEEDS_REVIEW: string;
    CLOSED: string;
  };
  dashboard: {
    title: string;
    subtitle: string;
    totalBusinesses: string;
    verified: string;
    unverified: string;
    needsReview: string;
    suspectedDuplicates: string;
    closed: string;
    collectionRuns: string;
    lastCollection: string;
    missingPhone: string;
    missingAddress: string;
    missingCoords: string;
    byWilayaTitle: string;
    sourceCoverageTitle: string;
    startCollectionCta: string;
    emptyNotice: string;
  };
  collect: {
    title: string;
    subtitle: string;
    selectWilayas: string;
    all69Wilayas: string;
    new11Wilayas: string;
    clearSelection: string;
    selectSources: string;
    searchDepth: string;
    depthQuick: string;
    depthStandard: string;
    depthDeep: string;
    startRun: string;
    stopRun: string;
    manualImportTitle: string;
    manualImportDesc: string;
    uploadFile: string;
  };
}

export const TRANSLATIONS: Record<AppLang, Translations> = {
  fr: {
    appName: 'DZ Car Rental Finder',
    nav: {
      dashboard: 'Tableau de bord',
      collect: 'Collecter',
      businesses: 'Agences',
      wilayas: 'Explorateur 69 Wilayas',
      map: 'Carte',
      duplicates: 'Doublons',
      verification: 'Vérification',
      review: 'Revue manuelle',
      exports: 'Centre d’export',
      sources: 'Sources',
      history: 'Historique',
      logs: 'Journaux',
      settings: 'Paramètres',
    },
    common: {
      search: 'Rechercher…',
      filter: 'Filtrer',
      reset: 'Réinitialiser',
      save: 'Enregistrer',
      cancel: 'Annuler',
      close: 'Fermer',
      refresh: 'Actualiser',
      loading: 'Chargement…',
      noData: 'Aucune donnée enregistrée pour le moment.',
      actions: 'Actions',
      all: 'Tous',
      yes: 'Oui',
      no: 'Non',
      download: 'Télécharger',
      wilaya: 'Wilaya',
      commune: 'Commune',
      status: 'Statut',
      source: 'Source',
      confidence: 'Confiance',
    },
    statuses: {
      VERIFIED: 'Vérifiée',
      UNVERIFIED: 'Non vérifiée',
      NEEDS_REVIEW: 'À vérifier',
      CLOSED: 'Fermée',
    },
    dashboard: {
      title: 'Vue d’ensemble du registre',
      subtitle: 'Couverture nationale des agences de location de voitures sur les 69 wilayas d’Algérie.',
      totalBusinesses: 'Agences uniques',
      verified: 'Vérifiées',
      unverified: 'Non vérifiées',
      needsReview: 'À vérifier',
      suspectedDuplicates: 'Doublons potentiels',
      closed: 'Fermées',
      collectionRuns: 'Collectes lancées',
      lastCollection: 'Dernière collecte',
      missingPhone: 'Téléphone manquant',
      missingAddress: 'Adresse manquante',
      missingCoords: 'GPS manquant',
      byWilayaTitle: 'Répartition par wilaya',
      sourceCoverageTitle: 'Couverture par source',
      startCollectionCta: 'Lancer une collecte',
      emptyNotice: 'La base locale SQLite est prête (69 wilayas, 1 541 communes). Lancez une collecte ou importez un fichier CSV/Excel pour commencer.',
    },
    collect: {
      title: 'Moteur de collecte automatisée',
      subtitle: 'Sélectionnez les wilayas, les sources autorisées et la profondeur de recherche.',
      selectWilayas: 'Wilayas cibles',
      all69Wilayas: 'Toutes les 69 wilayas',
      new11Wilayas: '11 nouvelles wilayas (59–69)',
      clearSelection: 'Effacer sélection',
      selectSources: 'Sources activées',
      searchDepth: 'Profondeur',
      depthQuick: 'Rapide',
      depthStandard: 'Standard',
      depthDeep: 'Approfondie',
      startRun: 'Démarrer la collecte',
      stopRun: 'Arrêter proprement',
      manualImportTitle: 'Import manuel (CSV / Excel / GeoJSON)',
      manualImportDesc: 'Importez vos propres fichiers ou fiches vérifiées manuellement sur Google Maps sans créer de doublons.',
      uploadFile: 'Importer un fichier',
    },
  },
  ar: {
    appName: 'مكتشف كراء السيارات الجزائر',
    nav: {
      dashboard: 'لوحة القيادة',
      collect: 'جمع البيانات',
      businesses: 'الوكالات',
      wilayas: 'مستكشف 69 ولاية',
      map: 'الخريطة',
      duplicates: 'التكرارات',
      verification: 'التحقق',
      review: 'المراجعة اليدوية',
      exports: 'مركز التصدير',
      sources: 'المصادر',
      history: 'سجل الجمع',
      logs: 'السجلات',
      settings: 'الإعدادات',
    },
    common: {
      search: 'بحث…',
      filter: 'تصفية',
      reset: 'إعادة ضبط',
      save: 'حفظ',
      cancel: 'إلغاء',
      close: 'إغلاق',
      refresh: 'تحديث',
      loading: 'جارٍ التحميل…',
      noData: 'لا توجد بيانات مسجلة حتى الآن.',
      actions: 'إجراءات',
      all: 'الكل',
      yes: 'نعم',
      no: 'لا',
      download: 'تنزيل',
      wilaya: 'الولاية',
      commune: 'البلدية',
      status: 'الحالة',
      source: 'المصدر',
      confidence: 'درجة الثقة',
    },
    statuses: {
      VERIFIED: 'موثقة',
      UNVERIFIED: 'غير موثقة',
      NEEDS_REVIEW: 'تحتاج مراجعة',
      CLOSED: 'مغلقة',
    },
    dashboard: {
      title: 'نظرة عامة على السجل الوطني',
      subtitle: 'اكتشاف وتنظيم وكالات كراء السيارات عبر جميع الولايات الـ 69 في الجزائر.',
      totalBusinesses: 'الوكالات الفريدة',
      verified: 'موثقة',
      unverified: 'غير موثقة',
      needsReview: 'تحتاج مراجعة',
      suspectedDuplicates: 'تكرارات محتملة',
      closed: 'مغلقة',
      collectionRuns: 'عمليات الجمع',
      lastCollection: 'آخر عملية جمع',
      missingPhone: 'بدون هاتف',
      missingAddress: 'بدون عنوان',
      missingCoords: 'بدون إحداثيات',
      byWilayaTitle: 'التوزيع حسب الولاية',
      sourceCoverageTitle: 'تغطية المصادر',
      startCollectionCta: 'بدء جمع البيانات',
      emptyNotice: 'قاعدة البيانات المحلية جاهزة (69 ولاية، 1541 بلدية). ابدأ عملية جمع أو استورد ملف CSV/Excel.',
    },
    collect: {
      title: 'محرك الجمع الآلي',
      subtitle: 'اختر الولايات المستهدفة والمصادر المفعلة وعمق البحث.',
      selectWilayas: 'الولايات المستهدفة',
      all69Wilayas: 'كل الولايات الـ 69',
      new11Wilayas: 'الولايات الـ 11 الجديدة (59–69)',
      clearSelection: 'مسح التحديد',
      selectSources: 'المصادر المفعلة',
      searchDepth: 'عمق البحث',
      depthQuick: 'سريع',
      depthStandard: 'قياسي',
      depthDeep: 'معمق',
      startRun: 'بدء الجمع',
      stopRun: 'إيقاف آمن',
      manualImportTitle: 'الاستيراد اليدوي (CSV / Excel / GeoJSON)',
      manualImportDesc: 'استورد ملفاتك الخاصة أو بيانات التحقق اليدوي مع حفظ المصدر وتجنب التكرار.',
      uploadFile: 'استيراد ملف',
    },
  },
  en: {
    appName: 'DZ Car Rental Finder',
    nav: {
      dashboard: 'Dashboard',
      collect: 'Collect Data',
      businesses: 'Businesses',
      wilayas: 'Wilaya Explorer',
      map: 'Map',
      duplicates: 'Duplicates',
      verification: 'Verification',
      review: 'Manual Review',
      exports: 'Export Center',
      sources: 'Sources',
      history: 'Collection History',
      logs: 'Logs',
      settings: 'Settings',
    },
    common: {
      search: 'Search…',
      filter: 'Filter',
      reset: 'Reset',
      save: 'Save',
      cancel: 'Cancel',
      close: 'Close',
      refresh: 'Refresh',
      loading: 'Loading…',
      noData: 'No records stored yet.',
      actions: 'Actions',
      all: 'All',
      yes: 'Yes',
      no: 'No',
      download: 'Download',
      wilaya: 'Wilaya',
      commune: 'Commune',
      status: 'Status',
      source: 'Source',
      confidence: 'Confidence',
    },
    statuses: {
      VERIFIED: 'Verified',
      UNVERIFIED: 'Unverified',
      NEEDS_REVIEW: 'Needs Review',
      CLOSED: 'Closed',
    },
    dashboard: {
      title: 'Registry Overview',
      subtitle: 'Car rental agency discovery, verification, and provenance tracking across all 69 Algerian wilayas.',
      totalBusinesses: 'Unique Businesses',
      verified: 'Verified',
      unverified: 'Unverified',
      needsReview: 'Needs Review',
      suspectedDuplicates: 'Suspected Duplicates',
      closed: 'Closed',
      collectionRuns: 'Collection Runs',
      lastCollection: 'Last Collection',
      missingPhone: 'Missing Phone',
      missingAddress: 'Missing Address',
      missingCoords: 'Missing GPS',
      byWilayaTitle: 'Businesses by Wilaya',
      sourceCoverageTitle: 'Source Coverage',
      startCollectionCta: 'Start Collection',
      emptyNotice: 'Local SQLite database initialized (69 wilayas, 1,541 communes). Start a collection run or import a CSV/Excel file to populate.',
    },
    collect: {
      title: 'Automated Collection Engine',
      subtitle: 'Select target wilayas, enabled compliant sources, and collection depth.',
      selectWilayas: 'Target Wilayas',
      all69Wilayas: 'All 69 Wilayas',
      new11Wilayas: 'New 11 Wilayas (59–69)',
      clearSelection: 'Clear Selection',
      selectSources: 'Enabled Sources',
      searchDepth: 'Search Depth',
      depthQuick: 'Quick',
      depthStandard: 'Standard',
      depthDeep: 'Deep',
      startRun: 'Start Collection Run',
      stopRun: 'Stop Safely',
      manualImportTitle: 'Manual Import (CSV / Excel / GeoJSON)',
      manualImportDesc: 'Import local spreadsheets or manual Google Maps verification files into the deduplication pipeline.',
      uploadFile: 'Upload File',
    },
  },
};
