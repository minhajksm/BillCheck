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
 * Picking the pages of a bill, from the camera, the gallery or the phone's
 * files.
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
   * A bill from the phone's files: a PDF the hospital sent, or a photo saved
   * from WhatsApp or downloads rather than the gallery.
   *
   * A PDF goes up as it is: the reader takes one directly, and re-rendering
   * it to images would only lose sharpness. A photo is prepared like any
   * other page, which also turns a HEIC into something the reader accepts.
   */
  const chooseFile = async (): Promise<ScannedPage[]> => {
    const result = await DocumentPicker.getDocumentAsync({
      type: ['application/pdf', 'image/*'],
      multiple: true,
      copyToCacheDirectory: true,
    });
    if (result.canceled) return [];
    const pdfs = result.assets.filter(
      (file) => (file.mimeType ?? '') === 'application/pdf' || /\.pdf$/i.test(file.name),
    );
    const images = result.assets.filter((file) => !pdfs.includes(file));

    const added: ScannedPage[] = pdfs.map((file) => ({
      uri: file.uri,
      name: file.name || 'bill.pdf',
      type: 'application/pdf',
    }));
    setPages((current) => [...current, ...added].slice(0, MAX_PAGES));
    if (images.length === 0) return added;
    // A file's size isn't known here; 0 x 0 re-encodes it without resizing.
    const prepared = await addAssets(
      images.map((file) => ({
        uri: file.uri,
        width: 0,
        height: 0,
        fileName: file.name,
        mimeType: file.mimeType ?? 'image/jpeg',
      })) as ImagePicker.ImagePickerAsset[],
    );
    return [...added, ...prepared];
  };

  const removePage = (index: number) => setPages((current) => current.filter((_, at) => at !== index));

  return { pages, preparing, takePhoto, choosePages, chooseFile, removePage };
}
