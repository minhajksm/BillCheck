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
 * lists. A spinner for that long reads as a hung app, so this says which of
 * the three it is on, and keeps saying it until the answer lands.
 *
 * Two rules it keeps. It never claims to be finished -- the last step goes on
 * working rather than completing, because only the response can end this. And
 * it never shows a percentage: nothing here knows how far along the reading
 * is, and a bar that stalls at 90% is worse than no bar.
 */

/** How long each step is given before the next takes over, in ms. */
const DWELL = [2600, 18000] as const;

const SWEEP = 2100;
const PULSE = 1800;

export function ReadingBill({ title }: { title?: string }) {
  const { t } = useTranslation();
  const palette = usePalette();
  const { width, height } = useWindowDimensions();
  const [step, setStep] = useState(0);
  const [still, setStill] = useState(false);

  const steps = STEPS.map((key) => t(key));

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

  // The steps advance on a timer because nothing reports progress back. The
  // dwell is set from what the reading actually costs, so the words on screen
  // are usually true -- and the last step simply stays, which is honest: it
  // is still working until the response arrives.
  useEffect(() => {
    if (step >= STEPS.length - 1) return;
    const timer = setTimeout(() => setStep((current) => current + 1), DWELL[step] ?? 8000);
    return () => clearTimeout(timer);
  }, [step]);

  // Announced on change only: on every render it would talk over the reader.
  useEffect(() => {
    AccessibilityInfo.announceForAccessibility(t(STEPS[step]));
  }, [step, t]);

  // A page the height of the card, swept top to bottom: the one gesture that
  // reads as "something is going through this line by line". Held in state
  // rather than a ref, as `toast.tsx` does -- a ref read during render is what
  // the lint rule is there to stop.
  const [sweep] = useState(() => new Animated.Value(0));
  const [pulse] = useState(() => new Animated.Value(0));

  useEffect(() => {
    if (still) return;
    const loop = Animated.loop(
      Animated.timing(sweep, {
        toValue: 1,
        duration: SWEEP,
        easing: Easing.inOut(Easing.ease),
        useNativeDriver: true,
      }),
    );
    const breathe = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 1,
          duration: PULSE,
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 0,
          duration: PULSE,
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    breathe.start();
    return () => {
      loop.stop();
      breathe.stop();
      sweep.setValue(0);
      pulse.setValue(0);
    };
  }, [still, sweep, pulse]);

  // Sized from the window rather than fixed, so it holds together on a small
  // phone, a tablet and a phone turned sideways.
  const paper = Math.min(width - 96, height * 0.3, 240);
  const line = Math.max(6, Math.round(paper / 26));

  return (
    <View style={styles.wrap} accessibilityRole="progressbar" accessibilityLabel={steps[step]}>
      <View
        style={[
          styles.paper,
          {
            width: paper,
            height: paper * 1.26,
            borderColor: palette.line,
            backgroundColor: palette.card,
          },
        ]}>
        {/* The bill itself, as rules of text. Decoration, so hidden from the
            screen reader, which is told the step instead. */}
        <View accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
          {RULES.map((rule, index) => (
            <View
              key={index}
              style={{
                height: line,
                marginBottom: line * 0.62,
                width: `${rule}%`,
                borderRadius: line / 2,
                backgroundColor: index % 4 === 2 ? palette.soft : palette.line,
              }}
            />
          ))}
        </View>

        {!still ? (
          <Animated.View
            style={[
              styles.sweep,
              {
                backgroundColor: palette.indigo,
                transform: [
                  {
                    translateY: sweep.interpolate({
                      inputRange: [0, 1],
                      outputRange: [0, paper * 1.26],
                    }),
                  },
                ],
                opacity: sweep.interpolate({
                  inputRange: [0, 0.1, 0.9, 1],
                  outputRange: [0, 1, 1, 0],
                }),
              },
            ]}
          />
        ) : null}
      </View>

      <Text variant="title" weight="bold" style={styles.heading} accessibilityRole="header">
        {title ?? t('reading.title')}
      </Text>
      <Text color="ink2" style={styles.note}>
        {t('reading.note')}
      </Text>

      <View style={styles.steps}>
        {steps.map((label, index) => {
          const done = index < step;
          const now = index === step;
          return (
            <View key={label} style={styles.step}>
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
                        opacity: pulse.interpolate({
                          inputRange: [0, 1],
                          outputRange: [1, 0.25],
                        }),
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

/** The three things the reading does, in the order it does them. */
const STEPS = ['reading.step1', 'reading.step2', 'reading.step3'] as const;

/** The widths of the lines on the drawn page, as percentages. */
const RULES = [88, 54, 96, 72, 90, 46, 94, 80, 62, 92, 70];

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 28,
    gap: 2,
  },
  paper: {
    borderWidth: 1,
    borderRadius: Radius.card,
    padding: 16,
    overflow: 'hidden',
    justifyContent: 'center',
  },
  sweep: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: 0,
    height: 2,
    opacity: 0.9,
  },
  heading: { marginTop: 26, textAlign: 'center' },
  note: { marginTop: 6, textAlign: 'center', lineHeight: 21 },
  steps: {
    marginTop: 26,
    gap: 14,
    alignSelf: 'stretch',
    maxWidth: 360,
    width: '100%',
  },
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
