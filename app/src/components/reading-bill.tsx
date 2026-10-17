import { useEffect, useState } from 'react';
import { AccessibilityInfo, Animated, Easing, StyleSheet, View, useWindowDimensions } from 'react-native';
import { useTranslation } from 'react-i18next';

import { Icon } from '@/components/icon';
import { Text } from '@/components/text';
import { Radius } from '@/constants/theme';
import { usePalette } from '@/hooks/use-palette';

/**
 * What a family watches while their bill is read.
 *
 * Reading a real bill takes most of a minute: the pages go up, a model
 * transcribes every line, and the lines are priced against the published
 * lists. A spinner for that long reads as a hung app, so the page is drawn
 * being read — a scanning head crosses it and each line lights as it is
 * picked up, then the sweep begins again. It runs until the answer lands;
 * nothing here stops on a timer.
 *
 * What the three steps are told by:
 *
 * - Sending the pages is measured. `sent` is the upload's own progress, and
 *   the step completes when the last byte is acknowledged.
 * - Reading every line starts exactly when the upload finishes, so that
 *   transition is real too.
 * - Checking against price lists is an estimate. The audit runs on the server
 *   after the read, and nothing reports it back, so it lights after a dwell
 *   drawn from what the reading usually costs. It is the one step on this
 *   screen that is a guess, and it never claims to have finished.
 */

/** How long the reading usually runs before the pricing starts, in ms. */
const READING_DWELL = 17000;

const SWEEP = 2600;
const PULSE = 1700;

/** The three things the reading does, in the order it does them. */
const STEPS = ['reading.step1', 'reading.step2', 'reading.step3'] as const;

/** The widths of the lines on the drawn page, as percentages. */
const RULES = [88, 54, 96, 72, 90, 46, 94, 80, 62, 92, 70];

export function ReadingBill({ sent = 0, title }: { sent?: number; title?: string }) {
  const { t } = useTranslation();
  const palette = usePalette();
  const { width, height } = useWindowDimensions();
  const [pricing, setPricing] = useState(false);
  const [still, setStill] = useState(false);

  const uploaded = sent >= 1;
  const step = !uploaded ? 0 : pricing ? 2 : 1;

  // Honour the system setting: the sweep and the pulse are decoration, and on
  // a phone set to reduce motion they are exactly the kind that causes harm.
  useEffect(() => {
    let alive = true;
    void AccessibilityInfo.isReduceMotionEnabled().then((on) => alive && setStill(on));
    const listener = AccessibilityInfo.addEventListener('reduceMotionChanged', setStill);
    return () => {
      alive = false;
      listener.remove();
    };
  }, []);

  // The only step nothing reports back. Timed from the end of the upload, so
  // it tracks the reading rather than the time the screen happened to appear.
  useEffect(() => {
    if (!uploaded) return;
    const timer = setTimeout(() => setPricing(true), READING_DWELL);
    return () => clearTimeout(timer);
  }, [uploaded]);

  // Announced on change only: on every render it would talk over the reader.
  useEffect(() => {
    AccessibilityInfo.announceForAccessibility(t(STEPS[step]));
  }, [step, t]);

  const [sweep] = useState(() => new Animated.Value(0));
  const [pulse] = useState(() => new Animated.Value(0));

  useEffect(() => {
    if (still) return;
    const scanning = Animated.loop(
      Animated.timing(sweep, {
        toValue: 1,
        duration: SWEEP,
        easing: Easing.inOut(Easing.quad),
        useNativeDriver: true,
      }),
    );
    const breathing = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: PULSE, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0, duration: PULSE, useNativeDriver: true }),
      ]),
    );
    scanning.start();
    breathing.start();
    return () => {
      scanning.stop();
      breathing.stop();
      sweep.setValue(0);
      pulse.setValue(0);
    };
  }, [still, sweep, pulse]);

  // Sized from the window rather than fixed, so it holds together on a small
  // phone, a tablet and a phone turned sideways.
  const paper = Math.min(width - 96, height * 0.3, 240);
  const tall = paper * 1.26;
  const line = Math.max(6, Math.round(paper / 26));

  const head = sweep.interpolate({ inputRange: [0, 1], outputRange: [0, tall] });

  return (
    <View style={styles.wrap} accessibilityRole="progressbar" accessibilityLabel={t(STEPS[step])}>
      <View style={{ width: paper, height: tall }}>
        <View style={[styles.paper, { borderColor: palette.line, backgroundColor: palette.card }]}>
          {/* The bill itself, as rules of text, each lighting as the head
              passes it. Decoration, so hidden from the screen reader, which
              is told the step instead. */}
          <View accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
            {RULES.map((rule, index) => {
              // Where this line sits down the page, and so when the head
              // reaches it.
              const at = (index + 0.5) / RULES.length;
              return (
                <View key={index} style={{ height: line, marginBottom: line * 0.62, width: `${rule}%` }}>
                  <View
                    style={[
                      StyleSheet.absoluteFill,
                      { borderRadius: line / 2, backgroundColor: palette.line },
                    ]}
                  />
                  {!still ? (
                    <Animated.View
                      style={[
                        StyleSheet.absoluteFill,
                        {
                          borderRadius: line / 2,
                          backgroundColor: palette.indigo,
                          // Lights as the head crosses it, and stays lit until
                          // the sweep comes round again: the page fills in,
                          // rather than one bar wandering over it.
                          opacity: sweep.interpolate({
                            inputRange: [Math.max(0, at - 0.06), at, 1],
                            outputRange: [0, 1, 1],
                            extrapolate: 'clamp',
                          }),
                        },
                      ]}
                    />
                  ) : null}
                </View>
              );
            })}
          </View>
        </View>

        {/* The scanning head: a bright edge with its own glow behind it. */}
        {!still ? (
          <Animated.View pointerEvents="none" style={[styles.head, { transform: [{ translateY: head }] }]}>
            <View style={[styles.glow, { backgroundColor: palette.indigo }]} />
            <View style={[styles.edge, { backgroundColor: palette.indigo }]} />
          </Animated.View>
        ) : null}

        {/* Corner brackets, framing the page as something being looked at. */}
        {CORNERS.map((corner, index) => (
          <Animated.View
            key={index}
            pointerEvents="none"
            style={[
              styles.corner,
              corner,
              {
                borderColor: palette.indigo,
                opacity: still ? 0.5 : pulse.interpolate({ inputRange: [0, 1], outputRange: [0.25, 0.9] }),
              },
            ]}
          />
        ))}
      </View>

      <Text variant="title" weight="bold" style={styles.heading} accessibilityRole="header">
        {title ?? t('reading.title')}
      </Text>
      <Text color="ink2" style={styles.note}>
        {t('reading.note')}
      </Text>

      <View style={styles.steps}>
        {STEPS.map((key, index) => {
          const done = index < step;
          const now = index === step;
          // The one figure on this screen that is known rather than guessed.
          const label =
            now && index === 0 && sent > 0
              ? t('reading.step1Sending', { percent: Math.round(sent * 100) })
              : t(key);
          return (
            <View key={key} style={styles.step}>
              <View
                style={[
                  styles.dot,
                  { borderColor: done || now ? palette.indigo : palette.line },
                  done && { backgroundColor: palette.indigo },
                ]}>
                {done ? <Icon name="check" size={11} color="onIndigo" /> : null}
                {now && !still ? (
                  <Animated.View
                    style={[
                      styles.beat,
                      {
                        backgroundColor: palette.indigo,
                        opacity: pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 0.25] }),
                      },
                    ]}
                  />
                ) : null}
                {now && still ? <View style={[styles.beat, { backgroundColor: palette.indigo }]} /> : null}
              </View>
              <Text
                color={done || now ? 'ink' : 'ink3'}
                weight={now ? 'semibold' : 'regular'}
                style={styles.stepText}>
                {label}
              </Text>
            </View>
          );
        })}
      </View>
    </View>
  );
}

/** The four brackets, as the borders each one draws. */
const CORNERS = [
  { top: -5, left: -5, borderTopWidth: 2, borderLeftWidth: 2 },
  { top: -5, right: -5, borderTopWidth: 2, borderRightWidth: 2 },
  { bottom: -5, left: -5, borderBottomWidth: 2, borderLeftWidth: 2 },
  { bottom: -5, right: -5, borderBottomWidth: 2, borderRightWidth: 2 },
] as const;

const styles = StyleSheet.create({
  wrap: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 28, gap: 2 },
  paper: {
    flex: 1,
    borderWidth: 1,
    borderRadius: Radius.card,
    padding: 16,
    overflow: 'hidden',
    justifyContent: 'center',
  },
  head: { position: 'absolute', left: 0, right: 0, top: 0 },
  glow: { height: 26, marginTop: -26, opacity: 0.14 },
  edge: { height: 2, opacity: 0.95 },
  corner: { position: 'absolute', width: 14, height: 14, borderRadius: 3 },
  heading: { marginTop: 30, textAlign: 'center' },
  note: { marginTop: 6, textAlign: 'center', lineHeight: 21 },
  steps: { marginTop: 26, gap: 14, alignSelf: 'stretch', maxWidth: 360, width: '100%' },
  step: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  dot: {
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  beat: { width: 8, height: 8, borderRadius: 4 },
  stepText: { flex: 1 },
});
