import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useToast } from '@/components/toast';
import type { ScannedPage } from '@/data/cases-api';
import { preparePage } from '@/data/prepare-page';

/** A bill can be up to this many pages, here and in the API. */
export const MAX_PAGES = 12;

/**
 * Picking the pages of a bill, from the camera, the gallery or a PDF.
 *
 * Shared by the two screens that start a check: the home screen, where the
 * first page is picked, and the scan screen, where the rest are added. Each
 * picker returns what it added as well as keeping it, so a caller that only
 * wants the pages -- the home screen, which hands them straight on -- doesn't
 * have to watch state it isn't rendering.
 */
export function usePagePicker(initial: () => ScannedPage[] = () => []) {
  const { t } = useTranslation();
  const toast = useToast();
  const [pages, setPages] = useState<ScannedPage[]>(initial);
  const [preparing, setPreparing] = useState(false);

  const addAssets = async (assets: ImagePicker.ImagePickerAsset[]): Promise<ScannedPage[]> => {
    setPreparing(true);
    try {
      // Scaled down to what the reader uses, so a many-page bill uploads fast
      // and stays under the request limit.
      const added = await Promise.all(
        assets.map((asset, index) => {
          const pageNumber = pages.length + index + 1;
          return preparePage(asset, pageNumber, {
            uri: asset.uri,
            name: asset.fileName ?? `page-${pageNumber}.jpg`,
            type: asset.mimeType ?? 'image/jpeg',
          });
        }),
      );
      setPages((current) => [...current, ...added].slice(0, MAX_PAGES));
      return added;
    } finally {
      setPreparing(false);
    }
  };

  const takePhoto = async (): Promise<ScannedPage[]> => {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) {
      toast(t('scan.cameraDenied'));
      return [];
    }
    // Full quality here: the page is compressed once, when it is scaled down.
    const result = await ImagePicker.launchCameraAsync({ quality: 1 });
    return result.canceled ? [] : addAssets(result.assets);
  };

  const choosePages = async (): Promise<ScannedPage[]> => {
    const result = await ImagePicker.launchImageLibraryAsync({
      quality: 1,
      allowsMultipleSelection: true,
      selectionLimit: MAX_PAGES - pages.length,
    });
    return result.canceled ? [] : addAssets(result.assets);
  };

  /**
   * A bill handed over as a PDF. It goes up as it is: the reader takes a PDF
   * directly, and re-rendering it to images would only lose sharpness.
   */
  const choosePdf = async (): Promise<ScannedPage[]> => {
    const result = await DocumentPicker.getDocumentAsync({
      type: 'application/pdf',
      multiple: false,
      copyToCacheDirectory: true,
    });
    if (result.canceled) return [];
    const file = result.assets[0];
    const added: ScannedPage = {
      uri: file.uri,
      name: file.name || 'bill.pdf',
      type: 'application/pdf',
    };
    setPages((current) => [...current, added].slice(0, MAX_PAGES));
    return [added];
  };

  const removePage = (index: number) => setPages((current) => current.filter((_, at) => at !== index));

  return { pages, preparing, takePhoto, choosePages, choosePdf, removePage };
}
