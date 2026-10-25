import { useState } from 'react';
import { Modal, Pressable, StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Gutter, Radius } from '@/constants/theme';
import type { ScannedPage } from '@/data/cases-api';
import type { usePagePicker } from '@/hooks/use-page-picker';
import { usePalette } from '@/hooks/use-palette';

import { Button } from './button';
import { Icon, type IconName } from './icon';
import { Text } from './text';

type Picker = ReturnType<typeof usePagePicker>;

/**
 * One button for every way a page arrives: the camera, the gallery, or the
 * phone's files.
 *
 * Families get bills every way there is -- handed over at the counter, sent
 * on WhatsApp, emailed as a PDF -- and three buttons side by side made them
 * choose before they knew what each did. This asks once, after the tap, with
 * the three spelled out.
 *
 * `onPicked` hears what was added, if anything; a cancelled picker adds
 * nothing and says nothing.
 */
export function AddPagesButton({
  label,
  picker,
  onPicked,
  variant = 'primary',
  icon = 'camera',
  beforePick,
}: {
  label: string;
  picker: Picker;
  onPicked?: (pages: ScannedPage[]) => void;
  variant?: 'primary' | 'secondary';
  icon?: IconName;
  /** Runs on the tap, before the sheet; returning false stops there (e.g. consent first). */
  beforePick?: () => boolean;
}) {
  const [open, setOpen] = useState(false);

  const pick = async (choose: () => Promise<ScannedPage[]>) => {
    // Closed first, so the camera or picker opens over the screen and the
    // sheet isn't still standing when it comes back.
    setOpen(false);
    const pages = await choose();
    if (pages.length > 0) onPicked?.(pages);
  };

  return (
    <>
      <Button
        variant={variant}
        icon={icon}
        label={label}
        loading={picker.preparing}
        onPress={() => {
          if (beforePick && !beforePick()) return;
          setOpen(true);
        }}
      />
      <SourceSheet
        visible={open}
        onClose={() => setOpen(false)}
        onCamera={() => void pick(picker.takePhoto)}
        onGallery={() => void pick(picker.choosePages)}
        onFile={() => void pick(picker.chooseFile)}
      />
    </>
  );
}

function SourceSheet({
  visible,
  onClose,
  onCamera,
  onGallery,
  onFile,
}: {
  visible: boolean;
  onClose: () => void;
  onCamera: () => void;
  onGallery: () => void;
  onFile: () => void;
}) {
  const { t } = useTranslation();
  const palette = usePalette();
  const insets = useSafeAreaInsets();
  if (!visible) return null;

  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.scrim} accessibilityLabel={t('common.cancel')} onPress={onClose} />
      {/* A Modal draws outside the screen's safe area, so it keeps its own. */}
      <View style={[styles.sheet, { backgroundColor: palette.app, paddingBottom: 16 + insets.bottom }]}>
        <Source icon="camera" label={t('pages.takePhoto')} onPress={onCamera} />
        <Source icon="image" label={t('pages.gallery')} onPress={onGallery} />
        <Source icon="file-text" label={t('pages.file')} hint={t('pages.fileHint')} onPress={onFile} />
        <View style={styles.cancel}>
          <Button variant="secondary" label={t('common.cancel')} onPress={onClose} />
        </View>
      </View>
    </Modal>
  );
}

function Source({
  icon,
  label,
  hint,
  onPress,
}: {
  icon: IconName;
  label: string;
  hint?: string;
  onPress: () => void;
}) {
  const palette = usePalette();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={({ pressed }) => [
        styles.source,
        { backgroundColor: pressed ? palette.soft : palette.card, borderColor: palette.line },
      ]}>
      <View style={[styles.sourceIcon, { backgroundColor: palette.indigoSoft }]}>
        <Icon name={icon} size={20} color="indigoInk" />
      </View>
      <View style={styles.sourceText}>
        <Text weight="semibold">{label}</Text>
        {hint ? <Text variant="faint">{hint}</Text> : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  scrim: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(14,16,32,0.45)',
  },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    borderTopLeftRadius: 22,
    borderTopRightRadius: 22,
    padding: Gutter,
    gap: 10,
  },
  source: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    borderWidth: 1,
    borderRadius: Radius.card,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  sourceIcon: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  sourceText: { flex: 1 },
  cancel: { marginTop: 4 },
});
