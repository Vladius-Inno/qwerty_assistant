from __future__ import annotations

import math
import flet as ft

from api_client import AuthClient
from config import settings


def main(page: ft.Page):
    page.title = "Qwerty WebApp"
    page.window_width = 420
    page.window_height = 700

    # Notification controls must be mounted first in Flet 0.28.x
    def _close_banner(_):
        page.banner.open = False
        page.update()

    page.snack_bar = ft.SnackBar(content=ft.Text(""), open=False)
    page.banner = ft.Banner(
        content=ft.Text(""),
        actions=[ft.TextButton("OK", on_click=_close_banner)],
        open=False,
    )
    page.dialog = ft.AlertDialog(title=ft.Text(""), content=ft.Text(""), open=False)
    # Add them to the page so they are part of the widget tree
    page.add(page.snack_bar, page.banner, page.dialog)

    # Client storage helpers (persist refresh token). Access token stays in memory only.
    def get_refresh_token() -> str | None:
        return page.client_storage.get("refresh_token")

    def set_refresh_token(value: str | None) -> None:
        if value:
            page.client_storage.set("refresh_token", value)
        else:
            page.client_storage.remove("refresh_token")

    client = AuthClient(
        base_url=settings.api_base_url,
        get_refresh_token=get_refresh_token,
        set_refresh_token=set_refresh_token,
    )

    # --- UI Controls ---
    email = ft.TextField(label="Email", autofocus=True, width=360)
    password = ft.TextField(label="Password", password=True, can_reveal_password=True, width=360)
    auth_error = ft.Text(color=ft.Colors.RED, size=12, visible=False)

    toggle_mode = ft.SegmentedButton(
        segments=[
            ft.Segment("login", label=ft.Text("Login")),
            ft.Segment("register", label=ft.Text("Register")),
        ],
        # Flet SegmentedButton expects a list for selected items even in single-select mode
        selected=["login"],
        allow_multiple_selection=False,
        width=360,
    )

    submit_btn = ft.ElevatedButton(text="Login", width=360)

    # Logo above auth form with diagonal label
    logo = ft.Container(
        width=360,
        padding=8,
        border=ft.border.all(1, ft.Colors.OUTLINE),
        border_radius=8,
        visible=True,
        clip_behavior=ft.ClipBehavior.NONE,
        content=ft.Stack(
            clip_behavior=ft.ClipBehavior.NONE,
            controls=[
                ft.Container(
                    alignment=ft.alignment.center,
                    content=ft.Image(src="qwerty.jpg", fit=ft.ImageFit.CONTAIN),
                ),
                ft.Container(
                    right=-55,
                    bottom=-10,
                    padding=2,
                    rotate=ft.Rotate(angle=-math.pi / 4),
                    content=ft.Text(
                        "Новости науки\nс Владимиром",
                        text_align=ft.TextAlign.CENTER,
                        weight=ft.FontWeight.BOLD,
                        size=22,
                    ),
                ),
            ]
        ),
    )

    # Home view
    me_view = ft.Column(controls=[], visible=False, width=360)

    def set_loading(loading: bool):
        submit_btn.disabled = loading
        page.update()

    def show_error(msg: str):
        auth_error.value = msg
        auth_error.visible = True
        page.update()

    def show_notice(msg: str):
        # Update mounted SnackBar then open and update once
        try:
            if isinstance(page.snack_bar.content, ft.Text):
                page.snack_bar.content.value = msg
            else:
                page.snack_bar.content = ft.Text(msg)
            page.snack_bar.open = True
            page.update()
        except Exception:
            # As last resort, attempt Banner or Dialog which are also mounted
            try:
                if isinstance(page.banner.content, ft.Text):
                    page.banner.content.value = msg
                else:
                    page.banner.content = ft.Text(msg)
                page.banner.open = True
                page.update()
            except Exception:
                try:
                    page.dialog.title = ft.Text("Notice")
                    if isinstance(page.dialog.content, ft.Text):
                        page.dialog.content.value = msg
                    else:
                        page.dialog.content = ft.Text(msg)
                    page.dialog.open = True
                    page.update()
                except Exception:
                    # Nothing else to do
                    page.update()

    def clear_error():
        auth_error.value = ""
        auth_error.visible = False
        page.update()

    def switch_to_login_with_notice(message: str):
        auth_error.visible = False
        # Switch to login mode and refresh related UI first
        toggle_mode.selected = ["login"]
        on_toggle_change(None)
        # Now show notification reliably
        show_notice(message)

    def on_toggle_change(e: ft.ControlEvent):
        # selected is a list (single item in single-select mode)
        selected_values = toggle_mode.selected or []
        submit_btn.text = "Register" if "register" in selected_values else "Login"
        clear_error()
        page.update()

    toggle_mode.on_change = on_toggle_change

    def show_auth_view():
        me_view.visible = False
        logo.visible = True
        form.visible = True
        clear_error()
        page.update()

    def show_me_view(me: dict):
        form.visible = False
        logo.visible = False
        me_view.controls.clear()
        me_view.controls.append(ft.Text("You are logged in.", weight=ft.FontWeight.BOLD))
        me_view.controls.append(ft.Text(f"Email: {me.get('email')}", selectable=True))
        me_view.controls.append(ft.Text(f"Active: {me.get('is_active')}"))
        me_view.controls.append(ft.Text(f"User ID: {me.get('id')}", selectable=True))

        def do_logout_all(_):
            client.logout(all_sessions=True)
            show_auth_view()

        def do_logout_session(_):
            client.logout(all_sessions=False)
            show_auth_view()

        me_view.controls.append(
            ft.Row(
                controls=[
                    ft.ElevatedButton("Logout session", on_click=do_logout_session),
                    ft.OutlinedButton("Logout all", on_click=do_logout_all),
                ]
            )
        )
        me_view.visible = True

    def do_submit(_):
        clear_error()
        if not email.value or not password.value:
            show_error("Email and password are required")
            return
        set_loading(True)
        try:
            if "register" in (toggle_mode.selected or []):
                client.register(email.value.strip(), password.value)
            else:
                client.login(email.value.strip(), password.value)
            me = client.get_me()
            if me:
                show_me_view(me)
            else:
                show_error("Failed to fetch profile after auth")
        except Exception as ex:  # httpx raises for 4xx on raise_for_status
            msg = str(ex)
            # If duplicate registration, inform and switch to login
            if "already registered" in msg.lower():
                switch_to_login_with_notice("The user already exists, please login")
            else:
                show_error(msg)
        finally:
            set_loading(False)

    submit_btn.on_click = do_submit
    # Trigger submit when pressing Enter in the password field
    password.on_submit = do_submit

    form = ft.Column(
        alignment=ft.MainAxisAlignment.START,
        spacing=10,
        width=360,
        controls=[
            ft.Text("Qwerty Science News DB", size=20, weight=ft.FontWeight.BOLD),
            toggle_mode,
            email,
            password,
            submit_btn,
            auth_error,
        ],
    )

    page.add(ft.Container(content=logo, padding=20, alignment=ft.alignment.top_center))
    page.add(ft.Container(content=form, padding=20, alignment=ft.alignment.top_center))
    page.add(ft.Container(content=me_view, padding=20, alignment=ft.alignment.top_left))

    # Try silent sign-in using refresh token
    try:
        if client.refresh():
            me = client.get_me()
            if me:
                show_me_view(me)
    except Exception:
        pass


if __name__ == "__main__":
    # Launch in the default web browser; register assets folder for images
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, 
    assets_dir="assets"
    )
