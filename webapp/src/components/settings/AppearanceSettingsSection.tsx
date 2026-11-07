import { CheckIcon, MonitorIcon, MoonStarIcon, PaletteIcon, SunIcon } from "lucide-react";
import { themeOptions, useTheme, type AppTheme } from "../ThemeProvider";
import { SettingsPanel, SettingsSection } from "./settings-layout";
import { ToggleGroup, ToggleGroupItem } from "../ui/toggle-group";

const themeDescriptions: Record<AppTheme, string> = {
  system: "Follow the browser or operating system preference.",
  prism: "The default high-contrast prism palette.",
  light: "A bright theme for daytime work.",
  dark: "A dim theme for low-light environments.",
};

const themeIcons = {
  system: MonitorIcon,
  prism: PaletteIcon,
  light: SunIcon,
  dark: MoonStarIcon,
} satisfies Record<AppTheme, typeof PaletteIcon>;

export function AppearanceSettingsSection() {
  const { theme, setTheme } = useTheme();

  return (
    <SettingsSection>
      <SettingsPanel title="Appearance" description="Choose the interface color theme.">
        <ToggleGroup
          type="single"
          value={theme}
          onValueChange={(value) => {
            if (value) {
              setTheme(value as AppTheme);
            }
          }}
          variant="outline"
          spacing={2}
          className="grid w-full grid-cols-1 sm:grid-cols-2"
          aria-label="Theme"
        >
          {themeOptions.map((option) => {
            const Icon = themeIcons[option.value];
            const selected = theme === option.value;
            return (
              <ToggleGroupItem
                key={option.value}
                value={option.value}
                className="h-auto w-full"
                data-theme-option={option.value}
                aria-label={`${option.label} theme`}
              >
                <span className="flex w-full flex-col items-start gap-1 py-2 text-left">
                  <span className="flex w-full items-center gap-2 font-medium">
                    <Icon data-icon="inline-start" aria-hidden="true" />
                    <span className="flex-1">{option.label}</span>
                    {selected && <CheckIcon aria-hidden="true" />}
                  </span>
                  <span className="text-xs font-normal whitespace-normal text-muted-foreground">
                    {themeDescriptions[option.value]}
                  </span>
                </span>
              </ToggleGroupItem>
            );
          })}
        </ToggleGroup>
      </SettingsPanel>
    </SettingsSection>
  );
}
