from __future__ import annotations

import asyncio
import math
import flet as ft

from api_client import AuthClient
from config import settings


def main(page: ft.Page):
    page.title = "Qwerty Assistant"
    page.window_width = 1000
    page.window_height = 720
    # Make content area lighter than the app bar for better contrast (with fallback for older Flet)
    content_bg = getattr(ft.Colors, "SURFACE_CONTAINER_LOW", getattr(ft.Colors, "SURFACE", ft.Colors.WHITE))
    page.bgcolor = content_bg

    # Global notifications
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
    page.add(page.snack_bar, page.banner, page.dialog)

    # Token persistence (refresh only)
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

    # ----- Auth UI -----
    email = ft.TextField(label="Email", autofocus=True, width=360)
    password = ft.TextField(label="Password", password=True, can_reveal_password=True, width=360)
    auth_error = ft.Text(color=ft.Colors.RED, size=12, visible=False)
    toggle_mode = ft.SegmentedButton(
        segments=[ft.Segment("login", label=ft.Text("Login")), ft.Segment("register", label=ft.Text("Register"))],
        selected=["login"],
        allow_multiple_selection=False,
        width=360,
    )
    submit_btn = ft.ElevatedButton(text="Login", width=360)

    def on_toggle_change(_):
        selected_values = toggle_mode.selected or []
        submit_btn.text = "Register" if "register" in selected_values else "Login"
        auth_error.value = ""
        auth_error.visible = False
        page.update()

    toggle_mode.on_change = on_toggle_change

    def show_error(msg: str):
        auth_error.value = msg
        auth_error.visible = True
        page.update()

    def show_notice(msg: str):
        if isinstance(page.snack_bar.content, ft.Text):
            page.snack_bar.content.value = msg
        else:
            page.snack_bar.content = ft.Text(msg)
        page.snack_bar.open = True
        page.update()

    def switch_to_login_with_notice(message: str):
        # Switch UI to login tab and notify via SnackBar
        toggle_mode.selected = ["login"]
        on_toggle_change(None)
        show_notice(message)

    form = ft.Column(
        controls=[toggle_mode, email, password, submit_btn, auth_error],
        width=360,
        spacing=10,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

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
            ],
        ),
    )

    # ----- Main UI -----
    current_user: dict | None = None
    
    # Profile menu: custom overlay anchored under the AppBar's right side
    def _logout_session(_):
        client.logout(all_sessions=False)
        _hide_profile_menu()
        show_auth_view()

    def _logout_all(_):
        client.logout(all_sessions=True)
        _hide_profile_menu()
        show_auth_view()

    profile_menu_content = ft.Column(spacing=6, tight=True, width=320)

    def _update_profile_menu():
        profile_menu_content.controls.clear()
        if current_user:
            profile_menu_content.controls.extend([
                ft.Text(f"Email: {current_user.get('email')}", selectable=True),
                ft.Text(f"Active: {current_user.get('is_active')}", selectable=False),
                ft.Text(f"User ID: {current_user.get('id')}", selectable=True),
                ft.Divider(),
                ft.Row(
                    [
                        ft.TextButton("Logout session", on_click=_logout_session),
                        ft.TextButton("Logout all", on_click=_logout_all),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                ),
            ])
        else:
            profile_menu_content.controls.append(ft.Text("Not signed in"))

    # Profile dropdown card with header and a close (X) button
    def _close_profile_menu(_):
        _hide_profile_menu()

    profile_menu_header = ft.Row(
        controls=[
            ft.Text("Profile", weight=ft.FontWeight.BOLD),
            ft.Container(expand=True),
            ft.IconButton(icon=ft.Icons.CLOSE, tooltip="Close", on_click=_close_profile_menu, icon_size=16),
        ],
        alignment=ft.MainAxisAlignment.START,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    profile_menu_card = ft.Card(
        visible=False,
        width=320,
        content=ft.Container(
            padding=10,
            content=ft.Column(controls=[profile_menu_header, profile_menu_content], spacing=8, tight=True),
        ),
    )

    # Overlay host: full-screen Stack with a clickable background that closes the menu
    def _on_overlay_bg_click(_):
        _hide_profile_menu()

    overlay_bg = ft.Container(
        expand=True,
        # Slight scrim (captures clicks reliably on web and desktop)
        bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.BLACK),
        on_click=_on_overlay_bg_click,
    )
    anchored_card = ft.Container(
        alignment=ft.alignment.top_right,
        # Position card right under the app bar and slightly inset from right
        padding=ft.padding.only(top=56, right=8),
        content=profile_menu_card,
    )
    overlay_host = ft.Stack(controls=[overlay_bg, anchored_card], expand=True, visible=False)
    page.overlay.append(overlay_host)

    def _toggle_profile_menu(_):
        if not profile_menu_card.visible:
            _update_profile_menu()
            profile_menu_card.visible = True
            overlay_host.visible = True
        else:
            profile_menu_card.visible = False
            overlay_host.visible = False
        page.update()

    def _hide_profile_menu():
        if profile_menu_card.visible or overlay_host.visible:
            profile_menu_card.visible = False
            overlay_host.visible = False
            page.update()

    profile_button = ft.IconButton(icon=ft.Icons.ACCOUNT_CIRCLE, tooltip="Profile", on_click=_toggle_profile_menu, disabled=True)
    appbar = ft.AppBar(title=ft.Text("Qwerty Assistant"), actions=[profile_button])

    # Research view: right messages + input (interactive area)
    messages_col = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
    progress_row = ft.Row([ft.ProgressRing()], alignment=ft.MainAxisAlignment.START, visible=False)
    input_field = ft.TextField(hint_text="Type your research request...", multiline=True, min_lines=1, max_lines=7, expand=True)
    send_btn = ft.IconButton(icon=ft.Icons.SEND, tooltip="Send")

    input_row = ft.Row(controls=[input_field, send_btn], alignment=ft.MainAxisAlignment.START)
    right_area = ft.Column(controls=[messages_col, progress_row, input_row], expand=True, spacing=10)

    # Database placeholder view (replaces right_area when selected from menu)
    database_view = ft.Container(
        content=ft.Text("Database view coming soon..."),
        alignment=ft.alignment.center,
        expand=True,
    )

    # Left sidebar: upper small menu, lower larger chats placeholder
    selected_section = "research"

    def _set_section(name: str):
        nonlocal selected_section, main_content, research_btn, database_btn
        selected_section = name
        main_content.content = right_area if name == "research" else database_view
        research_btn.text = "Research" + (" ✓" if name == "research" else "")
        database_btn.text = "Database" + (" ✓" if name == "database" else "")
        page.update()

    research_btn = ft.TextButton(text="Research ✓", on_click=lambda e: _set_section("research"))
    database_btn = ft.TextButton(text="Database", on_click=lambda e: _set_section("database"))

    menu_panel = ft.Container(
        padding=10,
        content=ft.Column(
            controls=[ft.Text("Menu", weight=ft.FontWeight.BOLD), research_btn, database_btn],
            spacing=6,
        ),
    )

    chats_list = ft.ListView(controls=[ft.ListTile(title=ft.Text(f"Chat {i+1}")) for i in range(5)], expand=True)
    chats_panel = ft.Container(
        padding=10,
        content=ft.Column(controls=[ft.Text("Chats", weight=ft.FontWeight.BOLD), ft.Container(height=6), chats_list], expand=True),
        expand=True,
    )

    left_sidebar = ft.Container(
        width=260,
        content=ft.Column(
            controls=[
                menu_panel,
                chats_panel,
            ],
            expand=True,
            spacing=8,
        ),
    )

    # Main content area that switches based on menu selection
    main_content = ft.Container(content=right_area, expand=True)
    main_view = ft.Row(controls=[left_sidebar, main_content], visible=False, expand=True)

    # Restoring session indicator (shown on startup if refresh token exists)
    restoring_box = ft.Column(
        controls=[
            ft.ProgressRing(),
            ft.Container(height=8),
            ft.Text("Restoring session..."),
        ],
        visible=False,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.CENTER,
        width=360,
    )

    # Message helpers
    def add_message(author: str, text: str):
        bg = ft.Colors.PRIMARY_CONTAINER if author == "agent" else ft.Colors.SECONDARY_CONTAINER
        align = ft.alignment.center_left if author == "agent" else ft.alignment.center_right
        label = "Agent" if author == "agent" else "You"
        bubble = ft.Container(
            content=ft.Column(controls=[ft.Text(label, size=11, color=ft.Colors.ON_SURFACE_VARIANT), ft.Text(text, selectable=True, width=600)]),
            bgcolor=bg,
            padding=10,
            border_radius=8,
            alignment=align,
        )
        messages_col.controls.append(bubble)
        page.update()

    sending = False

    def set_sending(value: bool):
        nonlocal sending
        sending = value
        input_field.disabled = value
        send_btn.disabled = value
        progress_row.visible = value
        page.update()

    async def run_agent_task(prompt: str):
        try:
            resp = await asyncio.to_thread(client.agent_loop, prompt, 3)
        except Exception as e:
            add_message("agent", f"Error: {e}")
            set_sending(False)
            return
        result = resp.get("result") if isinstance(resp, dict) else None
        add_message("agent", str(result) if result else "No response.")
        set_sending(False)

    def do_send(_):
        if sending:
            return
        prompt = (input_field.value or "").strip()
        if not prompt:
            return
        add_message("user", prompt)
        input_field.value = ""
        page.update()
        set_sending(True)
        async def _send_task():
            await run_agent_task(prompt)
        page.run_task(_send_task)

    send_btn.on_click = do_send

    # ----- View switching -----
    def show_auth_view():
        page.appbar = None
        main_view.visible = False
        logo.visible = True
        form.visible = True
        profile_button.disabled = True
        _hide_profile_menu()
        # ensure restoring indicator is hidden when showing auth
        restoring_box.visible = False
        # restore spacers for auth screen (use visibility instead of zero-height containers)
        top_spacer.visible = True
        auth_gap.visible = True
        page.update()

    def show_main_view(me: dict | None):
        nonlocal current_user
        current_user = me or {}
        form.visible = False
        logo.visible = False
        # hide restoring indicator if it was shown
        restoring_box.visible = False
        # refresh profile menu with user info and ensure it's hidden initially
        _update_profile_menu()
        _hide_profile_menu()
        profile_button.disabled = False
        page.appbar = appbar
        main_view.visible = True
        # remove spacers from layout for main screen
        top_spacer.visible = False
        auth_gap.visible = False
        page.update()

    def do_submit(_):
        auth_error.value = ""
        auth_error.visible = False
        if not email.value or not password.value:
            show_error("Email and password are required")
            return
        submit_btn.disabled = True
        page.update()
        try:
            if "register" in (toggle_mode.selected or []):
                client.register(email.value, password.value)
                show_notice("Registration successful. You are now logged in.")
            else:
                client.login(email.value, password.value)
        except Exception as e:
            msg = str(e)
            if "Email already registered" in msg:
                switch_to_login_with_notice("Email already registered. Please log in.")
            else:
                show_error(msg)
            submit_btn.disabled = False
            page.update()
            return
        submit_btn.disabled = False
        me = client.get_me()
        if me:
            show_main_view(me)
        else:
            show_error("Failed to fetch profile; please try again")

    submit_btn.on_click = do_submit
    # Enter-to-submit on auth fields
    email.on_submit = do_submit
    password.on_submit = do_submit

    # Layout root with a top spacer that collapses on main view to bring tabs closer to the app bar
    top_spacer = ft.Container(height=10)
    auth_gap = ft.Container(height=10)
    root = ft.Column(
        controls=[top_spacer, logo, restoring_box, auth_gap, form, main_view],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.START,
        expand=True,
    )
    page.add(root)

    # Init
    on_toggle_change(None)
    # Seamless session restore: if a refresh token exists, try to restore before showing login form
    if get_refresh_token():
        def show_restoring(show: bool):
            restoring_box.visible = show
            logo.visible = not show
            form.visible = not show
            page.update()

        async def _restore():
            show_restoring(True)
            ok = False
            try:
                ok = await asyncio.to_thread(client.refresh)
            except Exception:
                ok = False
            me = None
            if ok:
                try:
                    me = await asyncio.to_thread(client.get_me)
                except Exception:
                    me = None
            if me:
                # hide restoring before switching to main
                show_restoring(False)
                show_main_view(me)
            else:
                show_restoring(False)

        page.run_task(_restore)

if __name__ == "__main__":
    # Allows running with: python qwerty_webapp/app/app.py
    # In Docker, FLET_SERVER_* env vars make it serve as a web app on the given port.
    ft.app(target=main)
