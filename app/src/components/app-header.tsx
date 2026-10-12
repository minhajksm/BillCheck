import { router } from 'expo-router';
import type { ReactNode } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';

import { Radius } from '@/constants/theme';
import { usePalette } from '@/hooks/use-palette';

import { Icon, type IconName } from './icon';
import { Text } from './text';

type AppHeaderProps = {
  title: ReactNode;
  showBack?: boolean;
  right?: ReactNode;
};

/** Sticky screen header: optional back button, title, optional right action. */
export function AppHeader({ title, showBack = false, right }: AppHeaderProps) {
  const palette = usePalette();
  const { t } = useTranslation();

  return (
    <View style={[styles.header, { backgroundColor: palette.app, paddingLeft: showBack ? 8 : 18 }]}>
      {showBack ? (
        <IconButton
          icon="chevron-left"
          label={t('common.back')}
          onPress={() => (router.canGoBack() ? router.back() : router.replace('/'))}
        />
      ) : null}
      <View style={styles.title}>
        {typeof title === 'string' ? (
          <Text variant="title" weight="bold" accessibilityRole="header" numberOfLines={1}>
            {title}
          </Text>
        ) : (
          title
        )}
      </View>
      {right}
    </View>
  );
}

type IconButtonProps = { icon: IconName; label: string; onPress: () => void };

export function IconButton({ icon, label, onPress }: IconButtonProps) {
  const palette = usePalette();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      hitSlop={4}
      onPress={onPress}
      style={({ pressed }) => [styles.iconButton, pressed && { backgroundColor: palette.soft }]}>
      <Icon name={icon} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    minHeight: 56,
    paddingVertical: 8,
    paddingRight: 12,
  },
  title: { flex: 1 },
  iconButton: {
    width: 40,
    height: 40,
    borderRadius: Radius.icon,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
