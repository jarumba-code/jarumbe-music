import React from 'react';
import { View, Text, StyleSheet, Modal, Pressable, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, typography } from '../constants/theme';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

export type ActionItem = {
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  onPress: () => void;
  destructive?: boolean;
};

export type ActionSheetProps = {
  visible: boolean;
  onClose: () => void;
  title?: string;
  subtitle?: string;
  actions: ActionItem[];
};

export function ActionSheet({ visible, onClose, title, subtitle, actions }: ActionSheetProps) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose}>
          <View style={[StyleSheet.absoluteFill, { backgroundColor: 'rgba(0,0,0,0.5)' }]} />
        </Pressable>
        <View style={[styles.sheet, { backgroundColor: colors.bgElevated, paddingBottom: insets.bottom || spacing.xl }]}>
          <View style={styles.handleWrap}>
            <View style={[styles.handle, { backgroundColor: colors.borderSubtle }]} />
          </View>
          
          {(title || subtitle) && (
            <View style={[styles.header, { borderBottomColor: colors.borderSubtle }]}>
              {title && <Text style={[styles.title, { color: colors.textPrimary }]} numberOfLines={1}>{title}</Text>}
              {subtitle && <Text style={[styles.subtitle, { color: colors.textSecondary }]} numberOfLines={1}>{subtitle}</Text>}
            </View>
          )}

          <ScrollView bounces={false}>
            {actions.map((action, idx) => (
              <Pressable
                key={idx}
                style={({ pressed }) => [styles.actionRow, pressed && { backgroundColor: colors.bgElevated2 }]}
                onPress={() => {
                  action.onPress();
                  onClose();
                }}>
                <Ionicons
                  name={action.icon}
                  size={24}
                  color={action.destructive ? colors.error : colors.textPrimary}
                  style={styles.actionIcon}
                />
                <Text style={[styles.actionLabel, { color: action.destructive ? colors.error : colors.textPrimary }]}>
                  {action.label}
                </Text>
              </Pressable>
            ))}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    justifyContent: 'flex-end',
  },
  sheet: {
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    maxHeight: '80%',
  },
  handleWrap: {
    alignItems: 'center',
    paddingVertical: spacing.sm,
  },
  handle: {
    width: 40,
    height: 4,
    borderRadius: 2,
  },
  header: {
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    marginBottom: spacing.sm,
  },
  title: {
    fontSize: typography.bodyBold.fontSize,
    fontWeight: typography.bodyBold.fontWeight,
    textAlign: 'center',
    marginBottom: 4,
  },
  subtitle: {
    fontSize: typography.caption.fontSize,
    textAlign: 'center',
  },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
  },
  actionIcon: {
    marginRight: spacing.md,
  },
  actionLabel: {
    fontSize: typography.body.fontSize,
  },
});
