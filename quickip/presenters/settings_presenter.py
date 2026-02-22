from quickip.domain.interfaces import IServiceContainer, ISettingsView
import customtkinter as ctk

class SettingsView(ISettingsView):
    def show_message(self, title: str, message: str): ...
    def show_error(self, message: str): ...

class SettingsPresenter:
    def __init__(self, view: SettingsView, context: IServiceContainer):
        self.view = view
        self.context = context

    def change_theme(self, theme: str):
        # UI palette in this project is token-driven in MainWindow.
        # Therefore we delegate actual re-theming to the view callback (wired by MainWindow).
        theme_norm = str(theme).strip().lower()
        mode = "dark" if theme_norm in {"dark", "тёмная", "темная"} else "light"

        # Persist preference
        try:
            self.context.settings_repo.set("ui_theme", mode)
            self.context.settings_repo.save()
        except Exception:
            pass

        # Apply via MainWindow callback if available
        if hasattr(self.view, "apply_theme"):
            try:
                self.view.apply_theme(mode)
            except Exception:
                pass
        else:
            # Fallback: global appearance only
            try:
                ctk.set_appearance_mode(mode)
            except Exception:
                pass

        try:
            self.view.show_message(self.context.i18n.get("success"), f"Theme changed to {mode}")
        except Exception:
            pass

    def change_language(self, locale_code: str):
        self.context.i18n.set_locale(locale_code)
        # Save preference
        self.context.settings_repo.set("language", locale_code)
        self.context.settings_repo.save()
        msg = self.context.i18n.get("msg_restart_lang")
        try:
            self.view.show_message(self.context.i18n.get("success"), msg)
        except Exception:
            pass

    def refresh_home_snapshot(self):
        """Called by MainWindow on init — no-op for settings."""
        pass
