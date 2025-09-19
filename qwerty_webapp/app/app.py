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
                        "\u041d\u043e\u0432\u043e\u0441\u0442\u0438 \u043d\u0430\u0443\u043a\u0438\n\u0441 \u0412\u043b\u0430\u0434\u0438\u043c\u0438\u0440\u043e\u043c",
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
    status_text = ft.Text("", size=12, selectable=False)
    readonly_label = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT, visible=False)
    progress_row = ft.Row([ft.ProgressRing(), ft.Container(width=8), status_text], alignment=ft.MainAxisAlignment.START, visible=False)
    chat_loading_text = ft.Text("Loading chat...", size=12, selectable=False)
    chat_loading_row = ft.Row([ft.ProgressRing(), ft.Container(width=8), chat_loading_text], alignment=ft.MainAxisAlignment.START, visible=False)
    input_field = ft.TextField(hint_text="Type your research request...", multiline=True, min_lines=1, max_lines=7, expand=True)
    send_btn = ft.IconButton(icon=ft.Icons.SEND, tooltip="Send")

    input_row = ft.Row(controls=[input_field, send_btn], alignment=ft.MainAxisAlignment.START)
    right_area = ft.Column(controls=[messages_col, progress_row, chat_loading_row, readonly_label, input_row], expand=True, spacing=10)

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
        research_btn.text = "Research" + (" \u2713" if name == "research" else "")
        database_btn.text = "Database" + (" \u2713" if name == "database" else "")
        page.update()

    research_btn = ft.TextButton(text="Research \u2713", on_click=lambda e: _set_section("research"))
    database_btn = ft.TextButton(text="Database", on_click=lambda e: _set_section("database"))

    menu_panel = ft.Container(
        padding=10,
        content=ft.Column(
            controls=[ft.Text("Menu", weight=ft.FontWeight.BOLD), research_btn, database_btn],
            spacing=6,
        ),
    )

    chats_list = ft.ListView(controls=[], expand=True)
    chats_data: list[dict] = []
    current_chat_id: str | None = None
    viewing_chat_id: str | None = None
    current_view_backup: list[ft.Control] | None = None

    def _render_chats():
        tiles: list[ft.Control] = []
        # Placeholder for returning to current conversation while it is in progress
        # Show placeholder before first agent reply (including before first send) and while sending
        show_current_placeholder = (not can_start_new_chat) or sending
        if show_current_placeholder:
            def _go_current(_):
                nonlocal viewing_chat_id, current_view_backup
                viewing_chat_id = current_chat_id
                if current_view_backup is not None:
                    messages_col.controls = current_view_backup
                    current_view_backup = None
                    update_input_enabled()
                    page.update()
                else:
                    # If no backup (e.g., app just started or nothing to restore), load persisted if exists
                    if current_chat_id:
                        async def _load():
                            await load_chat_messages(current_chat_id)
                        page.run_task(_load)
                    else:
                        update_input_enabled()
                        page.update()
            tiles.append(ft.ListTile(title=ft.Text("\u0422\u0435\u043a\u0443\u0449\u0438\u0439 \u0447\u0430\u0442"), on_click=_go_current))
            tiles.append(ft.Divider())
        for ch in chats_data:
            ch_id = str(ch.get("id"))
            name = ch.get("name") or "Chat"
            # Hide the current (in-progress) chat from the normal list until it completes
            if (not can_start_new_chat) and (current_chat_id is not None) and (ch_id == current_chat_id):
                continue
            def _make_handler(chat_id: str):
                def _on_click(_):
                    nonlocal viewing_chat_id, current_view_backup
                    viewing_chat_id = chat_id
                    # Backup current view if switching away from active conversation
                    if current_view_backup is None and (current_chat_id is None or chat_id != current_chat_id):
                        current_view_backup = list(messages_col.controls)
                    async def _load():
                        await load_chat_messages(chat_id)
                    page.run_task(_load)
                return _on_click
            tiles.append(ft.ListTile(title=ft.Text(name), on_click=_make_handler(ch_id)))
        if not tiles:
            tiles = [ft.Container(padding=10, content=ft.Text("No chats yet", color=ft.Colors.ON_SURFACE_VARIANT, size=12))]
        chats_list.controls = tiles
        page.update()

    def refresh_chats():
        nonlocal chats_data
        data = client.chats_list()
        if isinstance(data, list):
            chats_data = data
            _render_chats()

    def create_new_chat(_=None):
        nonlocal current_chat_id, viewing_chat_id
        resp = client.chats_create()
        if not isinstance(resp, dict) or "id" not in resp:
            show_notice("Failed to create a new chat")
            return
        current_chat_id = str(resp["id"])
        viewing_chat_id = current_chat_id
        messages_col.controls.clear()
        update_input_enabled()
        page.update()
        refresh_chats()

    # New Chat control: enabled only after current chat completes (agent responded)
    can_start_new_chat = False
    def _update_new_chat_btn():
        new_chat_btn.disabled = not can_start_new_chat or sending
        page.update()

    def start_new_chat(_=None):
        nonlocal current_chat_id, viewing_chat_id, can_start_new_chat
        # Create a new chat immediately when starting a session/new chat
        try:
            resp = client.chats_create()
            if isinstance(resp, dict) and "id" in resp:
                current_chat_id = str(resp["id"])
                viewing_chat_id = current_chat_id
            else:
                current_chat_id = None
                viewing_chat_id = None
        except Exception:
            current_chat_id = None
            viewing_chat_id = None
        can_start_new_chat = False
        messages_col.controls.clear()
        update_input_enabled()
        _update_new_chat_btn()
        page.update()

    new_chat_btn = ft.ElevatedButton(text="New Chat", on_click=start_new_chat, disabled=True)
    chats_panel = ft.Container(
        padding=10,
        content=ft.Column(
            controls=[
                ft.Row([ft.Text("Chats", weight=ft.FontWeight.BOLD), new_chat_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Divider(),
                chats_list,
                ft.Divider(),
            ],
            expand=True,
        ),
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

    def is_read_only() -> bool:
        # Read-only when viewing a chat different from the active one, or when no active chat exists
        return (viewing_chat_id is not None) and (current_chat_id is None or viewing_chat_id != current_chat_id)

    def update_input_enabled():
        ro = is_read_only()
        input_field.disabled = ro or sending
        send_btn.disabled = ro or sending
        readonly_label.visible = ro and not sending
        if ro:
            readonly_label.value = "Viewing past chat — read-only"
        else:
            readonly_label.value = ""
        page.update()
        _update_new_chat_btn()

    def set_sending(value: bool):
        nonlocal sending
        sending = value
        update_input_enabled()
        _update_new_chat_btn()
        progress_row.visible = value
        page.update()

    async def load_chat_messages(chat_id: str):
        # Show loader while retrieving
        chat_loading_text.value = "Loading chat..."
        chat_loading_row.visible = True
        page.update()
        try:
            msgs = await asyncio.to_thread(client.chats_messages, chat_id)
            messages_col.controls.clear()
            if isinstance(msgs, list):
                for m in msgs:
                    role = str(m.get("role") or "agent")
                    content = str(m.get("content") or "")
                    add_message("user" if role == "user" else "agent", content)
            update_input_enabled()
        finally:
            chat_loading_row.visible = False
            page.update()

    async def run_agent_task(prompt: str):
        try:
            start_resp = await asyncio.to_thread(client.agent_loop_start, prompt, 3)
        except Exception as e:
            add_message("agent", f"Error starting job: {e}")
            set_sending(False)
            return
        if not isinstance(start_resp, dict) or "job_id" not in start_resp:
            add_message("agent", "Failed to start agent job.")
            set_sending(False)
            return
        job_id = start_resp["job_id"]

        # Poll status until done or error
        try:
            status_text.value = "Starting agent..."
            page.update()
            while True:
                status_resp = await asyncio.to_thread(client.agent_loop_status, job_id)
                if not isinstance(status_resp, dict):
                    await asyncio.sleep(1.5)
                    continue
                status = status_resp.get("status")
                msg = status_resp.get("message")
                if isinstance(msg, str) and msg:
                    status_text.value = msg
                    page.update()
                if status == "done":
                    result = status_resp.get("result")
                    add_message("agent", str(result) if result else "No response.")
                    break
                if status == "error":
                    add_message("agent", f"Error: {status_resp.get('error')}")
                    break
                await asyncio.sleep(1.5)
        finally:
            status_text.value = ""
            set_sending(False)

    def do_send(_):
        if sending:
            return
        prompt = (input_field.value or "").strip()
        if not prompt:
            return
        if is_read_only():
            show_notice("Cannot send in read-only chat; start a New Chat")
            return
        add_message("user", prompt)
        # Create chat on first send and save user message in background to avoid UI blocking
        created_now = False
        input_field.value = ""
        page.update()
        set_sending(True)
        async def _send_task():
            nonlocal current_chat_id, viewing_chat_id, created_now
            if not current_chat_id:
                try:
                    resp = await asyncio.to_thread(client.chats_create)
                    if isinstance(resp, dict) and "id" in resp:
                        current_chat_id = str(resp["id"])
                        viewing_chat_id = current_chat_id
                        created_now = True
                except Exception:
                    current_chat_id = None
            if current_chat_id:
                try:
                    await asyncio.to_thread(client.chats_add_message, current_chat_id, "user", prompt)
                except Exception:
                    pass
            await run_agent_task(prompt)
            # Persist last agent message into the chat
            if current_chat_id:
                try:
                    for ctrl in reversed(messages_col.controls):
                        if isinstance(ctrl, ft.Container) and isinstance(ctrl.content, ft.Column):
                            items = ctrl.content.controls
                            if len(items) >= 2 and isinstance(items[0], ft.Text) and items[0].value == "Agent" and isinstance(items[1], ft.Text):
                                await asyncio.to_thread(client.chats_add_message, current_chat_id, "agent", items[1].value or "")
                                break
                except Exception:
                    pass
            # Now that the chat has its first agent message, show it in the sidebar
            try:
                refresh_chats()
            except Exception:
                pass
            # Allow starting a new chat after this one completed a roundtrip
            nonlocal can_start_new_chat
            can_start_new_chat = True
            _update_new_chat_btn()
            # Mark the finished chat as read-only by clearing active chat id
            completed_chat_id = current_chat_id
            current_chat_id = None
            update_input_enabled()
            _render_chats()
            # Auto-rename chat to first user prompt (truncated) if this chat was just created
            try:
                if completed_chat_id and created_now:
                    first_line = (prompt or "").strip().replace("\n", " ")
                    if first_line:
                        new_name = first_line[:60]
                        await asyncio.to_thread(client.chats_rename, completed_chat_id, new_name)
                        refresh_chats()
            except Exception:
                pass
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
        # Start a new chat for this session and load sidebar (exclude current chat from list until completion)
        try:
            start_new_chat()
            refresh_chats()
        except Exception:
            pass

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
            # Proceed to main even if /me fails; tokens are set after login
            show_main_view({})
            show_notice("Logged in. Profile fetch failed; continuing anyway.")

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
    # Background session restore without blocking UI
    if get_refresh_token():
        async def _restore_bg():
            ok = False
            try:
                ok = await asyncio.wait_for(asyncio.to_thread(client.refresh), timeout=8.0)
            except Exception:
                ok = False
            if ok:
                try:
                    me = await asyncio.wait_for(asyncio.to_thread(client.get_me), timeout=8.0)
                except Exception:
                    me = None
                show_main_view(me or {})
        page.run_task(_restore_bg)

if __name__ == "__main__":
    # Allows running with: python qwerty_webapp/app/app.py
    # In Docker, FLET_SERVER_* env vars make it serve as a web app on the given port.
    ft.app(target=main)






