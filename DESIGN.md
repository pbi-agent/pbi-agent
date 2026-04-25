---
name: Prism Agent
colors:
  surface: '#0b1326'
  surface-dim: '#0b1326'
  surface-bright: '#31394d'
  surface-container-lowest: '#060e20'
  surface-container-low: '#131b2e'
  surface-container: '#171f33'
  surface-container-high: '#222a3d'
  surface-container-highest: '#2d3449'
  on-surface: '#dae2fd'
  on-surface-variant: '#c2c6d6'
  inverse-surface: '#dae2fd'
  inverse-on-surface: '#283044'
  outline: '#8c909f'
  outline-variant: '#424754'
  surface-tint: '#adc6ff'
  primary: '#adc6ff'
  on-primary: '#002e6a'
  primary-container: '#4d8eff'
  on-primary-container: '#00285d'
  inverse-primary: '#005ac2'
  secondary: '#b9c8de'
  on-secondary: '#233143'
  secondary-container: '#39485a'
  on-secondary-container: '#a7b6cc'
  tertiary: '#89ceff'
  on-tertiary: '#00344d'
  tertiary-container: '#009ada'
  on-tertiary-container: '#002d43'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#d8e2ff'
  primary-fixed-dim: '#adc6ff'
  on-primary-fixed: '#001a42'
  on-primary-fixed-variant: '#004395'
  secondary-fixed: '#d4e4fa'
  secondary-fixed-dim: '#b9c8de'
  on-secondary-fixed: '#0d1c2d'
  on-secondary-fixed-variant: '#39485a'
  tertiary-fixed: '#c9e6ff'
  tertiary-fixed-dim: '#89ceff'
  on-tertiary-fixed: '#001e2f'
  on-tertiary-fixed-variant: '#004c6e'
  background: '#0b1326'
  on-background: '#dae2fd'
  surface-variant: '#2d3449'
typography:
  h1:
    fontFamily: Inter
    fontSize: 2.25rem
    fontWeight: '700'
    lineHeight: 2.5rem
    letterSpacing: -0.02em
  h2:
    fontFamily: Inter
    fontSize: 1.5rem
    fontWeight: '600'
    lineHeight: 2rem
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Inter
    fontSize: 1.125rem
    fontWeight: '400'
    lineHeight: 1.75rem
  body-md:
    fontFamily: Inter
    fontSize: 1rem
    fontWeight: '400'
    lineHeight: 1.5rem
  body-sm:
    fontFamily: Inter
    fontSize: 0.875rem
    fontWeight: '400'
    lineHeight: 1.25rem
  code-md:
    fontFamily: JetBrains Mono
    fontSize: 0.875rem
    fontWeight: '450'
    lineHeight: 1.5rem
  label-caps:
    fontFamily: Inter
    fontSize: 0.75rem
    fontWeight: '600'
    lineHeight: 1rem
    letterSpacing: 0.05em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  container-padding: 2rem
  gutter: 1.5rem
  stack-sm: 0.5rem
  stack-md: 1rem
  stack-lg: 2rem
  grid-columns: '12'
---

## Brand & Style

This design system is engineered for the modern developer who demands precision, speed, and clarity. The aesthetic combines **Minimalism** with subtle **Glassmorphism** to create a high-performance workspace that feels both lightweight and authoritative. 

The brand personality is "The Silent Partner": it stays out of the way until needed, providing a calm, focused environment for complex problem-solving. By utilizing deep, monochromatic foundations paired with sharp, high-contrast accents, the interface evokes a sense of technical mastery and reliability. It avoids decorative "fluff," instead using generous whitespace and structural transparency to define hierarchy and flow.

## Colors

The palette is anchored by **Deep Slate**, providing a low-strain environment for long-duration coding sessions. The primary **Cobalt Blue** is reserved for actionable elements and primary states, ensuring high discoverability against the dark backdrop.

Secondary grays are tiered to define structural depth:
- **Text Primary:** White/Slate-50 for maximum readability.
- **Text Secondary:** Slate-400 for metadata and inactive states.
- **Borders:** Slate-700/800 for crisp, non-distracting containment.

The feedback palette uses vibrant, saturated hues but applies them sparingly (typically through small indicators or subtle glows) to maintain the sophisticated, pro-grade atmosphere.

## Typography

The typography system relies on **Inter** for all UI elements to ensure maximum legibility and a neutral, systematic feel. It utilizes a tight typographic scale to keep information density high without sacrificing whitespace.

**JetBrains Mono** (or an equivalent clean monospace) is utilized strictly for technical data, code snippets, and terminal outputs. This clear distinction between "Instructional/UI" and "Technical/Data" text helps users context-switch more efficiently. Headlines use slight negative letter-spacing for a more modern, "tight" editorial look, while labels utilize uppercase tracking to denote secondary metadata.

## Layout & Spacing

This design system employs a **Fluid Grid** model built on an 8px (0.5rem) base unit. This ensures all components scale predictably and maintain rhythmic vertical spacing. 

To achieve the "pro-grade" feel, whitespace has been intentionally increased in the following areas:
- **Sidebars and Toolbars:** Padding is set to a minimum of 16px to prevent a cramped "legacy tool" appearance.
- **Layout Containers:** A standard 32px (2rem) margin surrounds main content areas to create a sense of breathing room.
- **Sectioning:** Large gaps (32px+) are used between distinct functional blocks (e.g., Code Editor vs. Console) to mentally separate tasks.

## Elevation & Depth

Depth is communicated through **Tonal Layers** and **Subtle Blurs** rather than traditional heavy shadows. 

1.  **Background (Level 0):** The base color (#0F172A).
2.  **Surfaces (Level 1):** Slightly lighter slate (#1E293B) with a 1px border (#334155). Used for cards and secondary panels.
3.  **Floating Elements (Level 2):** Modals, popovers, and menus utilize a semi-transparent background with a **Backdrop Blur (12px - 20px)**. This creates a "glass" effect that maintains the user's context of the layer beneath.
4.  **Highlighting:** Instead of drop shadows, active elements may feature a very subtle inner glow or a 1px colored border in Cobalt Blue to indicate focus.

## Shapes

The design system adopts a **Rounded** (Level 2) approach to humanize the technical interface. 

- **Primary UI Elements:** Buttons, input fields, and small cards use a consistent 8px (0.5rem) radius.
- **Large Containers:** Main application panes or large modal windows use a 16px (1rem) radius.
- **Interactive States:** Hovering over list items or menu options should trigger a rounded background highlight of 6px to create a soft, modern interaction feel.
- **Tags/Status:** Use a more aggressive rounding (12px+) or pill-shape to distinguish them from functional buttons.

## Components

### Buttons
Primary buttons are solid Cobalt Blue with white text. Secondary buttons are "ghost" style with a 1px Slate border and a subtle background fill on hover.

### Input Fields
Inputs use a dark background (#020617) with a subtle 1px border. On focus, the border transitions to Cobalt Blue with a very soft blue outer glow (3px spread, 10% opacity).

### Cards & Panels
Cards should not use shadows. They are defined by their background color difference and a 1px border. Content inside cards should follow the 8px spacing rhythm.

### Code Blocks
The code editor and technical outputs use a darker, recessed background. Syntax highlighting should use a refined, desaturated palette (soft teals, purples, and oranges) that complements the Cobalt Blue primary color without competing for attention.

### Chips & Badges
Small, low-contrast indicators for status. Success states use a subtle green text with a 10% opacity green background, rather than a solid block of color.

### Terminal / Console
A dedicated section using JetBrains Mono, minimal padding, and a high-contrast cursor. It should feel like a distinct, high-performance environment within the broader UI.