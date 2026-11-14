'use client';

import { Button as BaseButton } from '@base-ui/react/button';
import { Input as BaseInput } from '@base-ui/react/input';
import { Select as BaseSelect } from '@base-ui/react/select';
import { themeContainer, themePart } from "./component-theme";
export {
  GraphicalProvider,
  useGraphicalTheme,
  useGraphicalIconTheme,
} from "./graphical-theme-provider";

// Keep the complete Base UI props, refs, render, and event contracts.
export const Button = themePart(BaseButton, 'button', 'control', 'ui-button');
export const ButtonLabel = themePart('span', 'button', 'label');
export const Input = themePart(BaseInput, 'input', 'control', 'ui-input');
export const Select = {
  ...BaseSelect,
  Label: themePart(BaseSelect.Label, 'select', 'label', 'ui-label'),
  Trigger: themePart(
    BaseSelect.Trigger,
    'select',
    'control',
    'ui-button ui-spread',
  ),
  Positioner: themeContainer(BaseSelect.Positioner, 'ui-positioner'),
  Popup: themePart(BaseSelect.Popup, 'select', 'popover', 'ui-popup ui-menu'),
  Item: themePart(BaseSelect.Item, 'select', 'option', 'ui-option'),
};
