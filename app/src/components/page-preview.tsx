import { Image, Pressable, StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';

import { Radius } from '@/constants/theme';
import type { ScannedPage } from '@/data/cases-api';
import { usePalette } from '@/hooks/use-palette';

import { Icon } from './icon';
import { Text } from './text';

/**
 * One captured page, waiting to be read: a bill's or a lab report's.
 *
 * The photograph itself, not a numbered box: a family has to be able to see
 * that the page is square in frame and the small print is legible before
 * spending a minute of waiting on it. A single page gets the full width,
 * because a thumbnail the size of a stamp proves nothing and left most of
 * the screen empty. A PDF has no picture to show, so it shows its name.
 */
export function PagePreview({
  page,
  number,
  alone,
  onRemove,
}: {
  page: ScannedPage;
  number: number;
  alone: boolean;
  onRemove: () => void;
}) {
  const { t } = useTranslation();
  const palette = usePalette();

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={t('scan.remove', { number })}
      onPress={onRemove}
      style={[
        styles.thumb,
        alone && styles.thumbAlone,
        { backgroundColor: palette.soft, borderColor: palette.line },
      ]}>
      {page.type.startsWith('image/') ? (
        // `contain`, not `cover`: a cropped preview would hide the very edge
        // a family is checking is in frame.
        <Image source={{ uri: page.uri }} style={styles.thumbImage} resizeMode="contain" />
      ) : (
        <View style={styles.thumbFile}>
          <Icon name="file-text" size={28} color="ink2" />
          <Text variant="faint" numberOfLines={2} style={styles.thumbName}>
            {page.name}
          </Text>
        </View>
      )}
      <View
        style={[styles.badge, styles.number, { backgroundColor: palette.app, borderColor: palette.line }]}>
        <Text variant="faint" weight="bold" color="ink2">
          {number}
        </Text>
      </View>
      <View
        style={[styles.badge, styles.remove, { backgroundColor: palette.app, borderColor: palette.line }]}>
        <Icon name="x" size={14} color="ink2" />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  thumb: {
    width: '48%',
    // About the shape of a bill page, so one of them fills the screen the way
    // the page it shows does.
    aspectRatio: 3 / 4,
    borderRadius: Radius.card,
    borderWidth: 1,
    overflow: 'hidden',
  },
  thumbAlone: { width: '100%' },
  thumbImage: { width: '100%', height: '100%' },
  thumbFile: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 8, padding: 12 },
  thumbName: { textAlign: 'center' },
  badge: {
    position: 'absolute',
    minWidth: 24,
    height: 24,
    borderRadius: 12,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  number: { top: 8, left: 8 },
  remove: { top: 8, right: 8 },
});
