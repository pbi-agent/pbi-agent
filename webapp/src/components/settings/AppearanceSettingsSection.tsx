import { CheckIcon, MoonStarIcon, PaletteIcon, SunIcon } from "lucide-react";
import { themeOptions, useTheme, type AppTheme } from "../ThemeProvider";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { ToggleGroup, ToggleGroupItem } from "../ui/toggle-group";

const themeDescriptions: Record<AppTheme, string> = {
  prism: "The default high-contrast prism palette.",
  light: "A bright theme for daytime work.",
  dark: "A dim theme for low-light environments.",
};

const themeIcons = {
  prism: PaletteIcon,
  light: SunIcon,
  dark: MoonStarIcon,
} satisfies Record<AppTheme, typeof PaletteIcon>;

export function AppearanceSettingsSection() {
  const { theme, setTheme } = useTheme();

  return (
    <section className="settings-section settings-section--active">
      <Card className="settings-panel">
        <CardHeader className="settings-panel__header">
          <div>
            <CardTitle className="settings-panel__title">Appearance</CardTitle>
            <CardDescription className="settings-panel__subtitle">
              Choose the interface color theme.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="settings-panel__body settings-appearance">
          <ToggleGroup
            type="single"
            value={theme}
            onValueChange={(value) => {
              if (value) {
                setTheme(value as AppTheme);
              }
            }}
            className="settings-appearance__theme-grid"
            aria-label="Theme"
          >
            {themeOptions.map((option) => {
              const Icon = themeIcons[option.value];
              const selected = theme === option.value;
              return (
                <ToggleGroupItem
                  key={option.value}
                  value={option.value}
                  className="settings-appearance__theme-option"
                  data-theme-option={option.value}
                  aria-label={`${option.label} theme`}
                >
                  <span className="settings-appearance__theme-option-head">
                    <Icon data-icon="inline-start" aria-hidden="true" />
                    <span className="settings-appearance__theme-option-label">
                      {option.label}
                    </span>
                    {selected && (
                      <CheckIcon
                        className="settings-appearance__theme-option-check"
                        aria-hidden="true"
                      />
                    )}
                  </span>
                  <span className="settings-appearance__theme-option-description">
                    {themeDescriptions[option.value]}
                  </span>
                </ToggleGroupItem>
              );
            })}
          </ToggleGroup>
        </CardContent>
      </Card>
    </section>
  );
}
