from __future__ import annotations

import asyncio
import math
import flet as ft

from typing import Callable, Optional

from api_client import AuthClient
from config import settings


# --- Testability hooks (dependency injection) ---
AuthClientFactory = Callable[[str, Callable[[], Optional[str]], Callable[[Optional[str]], None]], AuthClient]
_client_factory: Optional[AuthClientFactory] = None
_enable_auto_restore: bool = True


def set_client_factory(factory: AuthClientFactory) -> None:
    global _client_factory
    _client_factory = factory


def set_auto_restore(enabled: bool) -> None:
    global _enable_auto_restore
    _enable_auto_restore = enabled


def _make_client(base_url: str, get_refresh_token, set_refresh_token) -> AuthClient:
    if _client_factory is not None:
        return _client_factory(base_url, get_refresh_token, set_refresh_token)
    return AuthClient(base_url=base_url, get_refresh_token=get_refresh_token, set_refresh_token=set_refresh_token)


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

    client = _make_client(
        settings.api_base_url,
        get_refresh_token,
        set_refresh_token,
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

    # Database interactions view (left: interactions menu replaces chats; right: controls + results)
    db_selected_op: str = "combined"  # combined | related | keywords | by_id
    db_results_col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)

    # Controls per operation
    # Combined search controls
    db_comb_query = ft.TextField(label="Query", expand=True)
    db_comb_limit = ft.TextField(label="Limit", value="10", width=120)
    db_comb_preselect = ft.TextField(label="Preselect", value="200", width=120)
    db_comb_alpha = ft.Slider(min=0.0, max=1.0, divisions=20, value=0.7, label="{value}")
    db_comb_exec = ft.ElevatedButton(text="Execute")

    # Related controls
    db_rel_id = ft.TextField(label="Article ID", width=180)
    db_rel_method = ft.Dropdown(label="Method", width=160, options=[ft.dropdown.Option("semantic"), ft.dropdown.Option("cooccur")], value="semantic")
    db_rel_topn = ft.TextField(label="Top N", value="10", width=120)
    db_rel_exec = ft.ElevatedButton(text="Execute")

    # Keywords search controls
    db_kw_keywords = ft.TextField(label="Keywords (comma-separated)", expand=True)
    db_kw_mode = ft.Dropdown(label="Mode", width=140, options=[ft.dropdown.Option("any"), ft.dropdown.Option("all")], value="any")
    db_kw_partial = ft.Switch(label="Partial match", value=False)
    db_kw_limit = ft.TextField(label="Limit", value="20", width=120)
    db_kw_exec = ft.ElevatedButton(text="Execute")

    # Show by ID controls
    db_get_id = ft.TextField(label="Article ID", width=220)
    db_get_exec = ft.ElevatedButton(text="Load")

    db_controls_col = ft.Column(spacing=10)

    def _render_article_meta_row(item: dict) -> ft.Control:
        art_id_raw = item.get("id")
        try:
            art_id = int(art_id_raw)
        except Exception:
            art_id = None
        title = str(item.get("title") or "<no title>")
        date = str(item.get("date") or "")

        def _open(_):
            if art_id is not None:
                async def _open_task():
                    await load_article_detail(art_id)
                page.run_task(_open_task)

        return ft.ListTile(
            title=ft.Text(title),
            subtitle=ft.Text(f"ID: {art_id_raw}  Date: {date}"),
            on_click=_open,
        )

    db_detail_container = ft.Container(visible=False)
    db_content_stack = ft.Stack(controls=[], expand=True)

    def _show_db_list_view():
        db_detail_container.visible = False
        # controls area
        if db_selected_op == "combined":
            controls_row1 = ft.Row([db_comb_query])
            controls_row2 = ft.Row([db_comb_limit, db_comb_preselect])
            controls_row3 = ft.Row([ft.Text("Alpha"), db_comb_alpha, db_comb_exec])
            db_controls_col.controls = [ft.Text("Combined Search", weight=ft.FontWeight.BOLD), controls_row1, controls_row2, controls_row3]
        elif db_selected_op == "related":
            controls_row = ft.Row([db_rel_id, db_rel_method, db_rel_topn, db_rel_exec])
            db_controls_col.controls = [ft.Text("Related Articles", weight=ft.FontWeight.BOLD), controls_row]
        elif db_selected_op == "keywords":
            controls_row1 = ft.Row([db_kw_keywords])
            controls_row2 = ft.Row([db_kw_mode, db_kw_partial, db_kw_limit, db_kw_exec])
            db_controls_col.controls = [ft.Text("Keywords Search", weight=ft.FontWeight.BOLD), controls_row1, controls_row2]
        else:  # by_id
            controls_row = ft.Row([db_get_id, db_get_exec])
            db_controls_col.controls = [ft.Text("Show Article by ID", weight=ft.FontWeight.BOLD), controls_row]
        # mount list view
        list_panel = ft.Column(controls=[db_controls_col, ft.Divider(), db_results_col], expand=True, spacing=10)
        db_main_container.content = list_panel
        page.update()

    def _show_db_detail_view(data: dict):
        # data is ArticleFull
        back_btn = ft.TextButton(text="Back", icon=ft.Icons.ARROW_BACK, on_click=lambda e: _show_db_list_view())
        header = ft.Row([back_btn, ft.Text(str(data.get("title") or "Article"), weight=ft.FontWeight.BOLD)], alignment=ft.MainAxisAlignment.START)
        meta_items = []
        for key in ["id", "date", "release_number", "topic_name", "keywords", "tags", "summary", "source_link", "article_link"]:
            val = data.get(key)
            if val is None:
                continue
            meta_items.append(ft.Text(f"{key}: {val}"))
        body_text = ft.Text(str(data.get("body") or ""), selectable=True)
        db_detail_container.content = ft.Column(controls=[header, ft.Divider(), *meta_items, ft.Divider(), body_text], spacing=8, scroll=ft.ScrollMode.AUTO)
        db_detail_container.visible = True
        db_main_container.content = db_detail_container
        page.update()

    async def load_article_detail(article_id: int):
        art = await asyncio.to_thread(client.articles_get, article_id)
        if not art:
            show_notice("Article not found")
            return
        _show_db_detail_view(art)

    # Execute handlers
    async def _exec_combined():
        try:
            q = db_comb_query.value or ""
            limit = int(db_comb_limit.value or "10")
            preselect = int(db_comb_preselect.value or "200")
            alpha = float(db_comb_alpha.value or 0.7)
        except Exception:
            show_notice("Invalid parameters for combined search")
            return
        db_results_col.controls = [ft.Text("Loading..."), ft.ProgressRing()]
        page.update()
        # Prefer protected agent endpoint if available; fallback to public
        data = await asyncio.to_thread(client.agent_combined_search, q, limit, preselect, alpha)
        if not data:
            # try public
            data_list = await asyncio.to_thread(client.articles_combined_search, q, limit, preselect, alpha)
        else:
            data_list = data.get("result") if isinstance(data, dict) else None
        items = []
        if isinstance(data_list, list):
            for item in data_list:
                if isinstance(item, dict):
                    items.append(_render_article_meta_row(item))
        if not items:
            items = [ft.Text("No results")] 
        db_results_col.controls = items
        page.update()

    async def _exec_related():
        try:
            aid = int(db_rel_id.value or "0")
            topn = int(db_rel_topn.value or "10")
            method = db_rel_method.value or "semantic"
        except Exception:
            show_notice("Invalid parameters for related search")
            return
        db_results_col.controls = [ft.Text("Loading..."), ft.ProgressRing()]
        page.update()
        lst = await asyncio.to_thread(client.articles_related, aid, method, topn)
        items = []
        if isinstance(lst, list):
            for it in lst:
                if isinstance(it, dict):
                    items.append(_render_article_meta_row(it))
        if not items:
            items = [ft.Text("No results")] 
        db_results_col.controls = items
        page.update()

    async def _exec_keywords():
        try:
            kws_raw = db_kw_keywords.value or ""
            kws = [s.strip() for s in kws_raw.split(",") if s.strip()]
            mode = db_kw_mode.value or "any"
            partial = bool(db_kw_partial.value)
            limit = int(db_kw_limit.value or "20")
        except Exception:
            show_notice("Invalid parameters for keywords search")
            return
        db_results_col.controls = [ft.Text("Loading..."), ft.ProgressRing()]
        page.update()
        resp = await asyncio.to_thread(client.articles_search_keywords, keywords=kws, q=None, mode=mode, partial=partial, limit=limit)
        items = []
        if isinstance(resp, dict):
            data_list = resp.get("result")
            if isinstance(data_list, list):
                for it in data_list:
                    if isinstance(it, dict):
                        items.append(_render_article_meta_row(it))
        if not items:
            items = [ft.Text("No results")] 
        db_results_col.controls = items
        page.update()

    async def _exec_get():
        try:
            aid = int(db_get_id.value or "0")
        except Exception:
            show_notice("Invalid article id")
            return
        await load_article_detail(aid)

    db_comb_exec.on_click = lambda e: page.run_task(_exec_combined)
    db_rel_exec.on_click = lambda e: page.run_task(_exec_related)
    db_kw_exec.on_click = lambda e: page.run_task(_exec_keywords)
    db_get_exec.on_click = lambda e: page.run_task(_exec_get)

    db_main_container = ft.Container(expand=True)
    # Defer initial DB view rendering until Database section is selected

    # Left sidebar: upper small menu, lower larger chats placeholder
    selected_section = "research"

    def _set_section(name: str):
        nonlocal selected_section, main_content, research_btn, database_btn
        selected_section = name
        if name == "research":
            main_content.content = right_area
            chats_panel.visible = True
            db_panel.visible = False
        else:
            # Database mode: show db interactions in left, clear main to db view
            main_content.content = db_main_container
            chats_panel.visible = False
            db_panel.visible = True
            # Reset to default op view
            _show_db_list_view()
            _update_db_menu_labels()
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
    # Auto-rename management for newly created chats
    rename_pending: bool = False
    rename_source_prompt: str | None = None

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
        nonlocal current_chat_id, viewing_chat_id, can_start_new_chat, rename_pending, rename_source_prompt
        # Do NOT create a chat in DB yet; defer until agent loop completes
        current_chat_id = None
        viewing_chat_id = None
        rename_pending = False
        rename_source_prompt = None
        can_start_new_chat = False
        messages_col.controls.clear()
        update_input_enabled()
        _update_new_chat_btn()
        # Re-render sidebar so 'Текущий чат' placeholder appears immediately
        _render_chats()
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

    # Database interactions left panel (hidden by default)
    def _select_db_op(name: str):
        nonlocal db_selected_op
        db_selected_op = name
        _update_db_menu_labels()
        db_results_col.controls = []
        _show_db_list_view()

    def _update_db_menu_labels():
        combined_btn.text = ("• " if db_selected_op == "combined" else "  ") + "Combined Search"
        related_btn.text = ("• " if db_selected_op == "related" else "  ") + "Related Articles"
        keywords_btn.text = ("• " if db_selected_op == "keywords" else "  ") + "Keywords Search"
        byid_btn.text = ("• " if db_selected_op == "by_id" else "  ") + "Show by ID"

    combined_btn = ft.TextButton(text="Combined Search", on_click=lambda e: _select_db_op("combined"))
    related_btn = ft.TextButton(text="Related Articles", on_click=lambda e: _select_db_op("related"))
    keywords_btn = ft.TextButton(text="Keywords Search", on_click=lambda e: _select_db_op("keywords"))
    byid_btn = ft.TextButton(text="Show by ID", on_click=lambda e: _select_db_op("by_id"))
    _update_db_menu_labels()
    db_panel = ft.Container(
        padding=10,
        visible=False,
        content=ft.Column(
            controls=[
                ft.Text("Interactions", weight=ft.FontWeight.BOLD),
                ft.Divider(),
                combined_btn,
                related_btn,
                keywords_btn,
                byid_btn,
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
                db_panel,
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

        # Poll status until done or error with a guard against silent failures
        try:
            status_text.value = "Starting agent..."
            page.update()
            invalid_count = 0
            while True:
                status_resp = await asyncio.to_thread(client.agent_loop_status, job_id)
                if not isinstance(status_resp, dict):
                    invalid_count += 1
                    if invalid_count >= 8:  # ~12s with 1.5s sleep
                        add_message("agent", "Failed to fetch job status. Please try again.")
                        break
                    await asyncio.sleep(1.5)
                    continue
                invalid_count = 0
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
        nonlocal rename_pending, rename_source_prompt
        if sending:
            return
        prompt = (input_field.value or "").strip()
        if not prompt:
            return
        if is_read_only():
            show_notice("Cannot send in read-only chat; start a New Chat")
            update_input_enabled()
            return
        set_sending(True)
        status_text.value = "Starting agent..."
        add_message("user", prompt)
        if rename_pending and not rename_source_prompt:
            rename_source_prompt = prompt
        created_now = False
        input_field.value = ""
        page.update()
        async def _send_task():
            nonlocal current_chat_id, viewing_chat_id, created_now, rename_pending, rename_source_prompt
            ran_agent = False
            try:
                if not current_chat_id:
                    try:
                        resp = await asyncio.to_thread(client.chats_create)
                        if isinstance(resp, dict) and "id" in resp:
                            current_chat_id = str(resp["id"])
                            viewing_chat_id = current_chat_id
                            created_now = True
                            rename_pending = True
                            if not rename_source_prompt:
                                rename_source_prompt = prompt
                    except Exception:
                        current_chat_id = None
                if current_chat_id:
                    try:
                        await asyncio.to_thread(client.chats_add_message, current_chat_id, "user", prompt)
                    except Exception:
                        pass
                await run_agent_task(prompt)
                ran_agent = True
            except Exception:
                pass
            finally:
                if not ran_agent:
                    set_sending(False)
            if ran_agent and current_chat_id:
                try:
                    for ctrl in reversed(messages_col.controls):
                        if isinstance(ctrl, ft.Container) and isinstance(ctrl.content, ft.Column):
                            items = ctrl.content.controls
                            if len(items) >= 2 and isinstance(items[0], ft.Text) and items[0].value == "Agent" and isinstance(items[1], ft.Text):
                                await asyncio.to_thread(client.chats_add_message, current_chat_id, "agent", items[1].value or "")
                                break
                except Exception:
                    pass
            try:
                refresh_chats()
            except Exception:
                pass
            nonlocal can_start_new_chat
            can_start_new_chat = True
            _update_new_chat_btn()
            completed_chat_id = current_chat_id
            current_chat_id = None
            update_input_enabled()
            _render_chats()
            try:
                if completed_chat_id and rename_pending:
                    first_line = (rename_source_prompt or prompt or "").strip().replace("\n", " ")
                    if first_line:
                        new_name = first_line[:60]
                        await asyncio.to_thread(client.chats_rename, completed_chat_id, new_name)
                        rename_pending = False
                        rename_source_prompt = None
                        refresh_chats()
            except Exception:
                pass
        page.run_task(_send_task)

    send_btn.on_click = do_send
    # Allow Enter/Return to submit from the input field
    input_field.on_submit = do_send

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

    # Expose key handles for tests (non-breaking, ignored by Flet at runtime)
    try:
        from dataclasses import dataclass

        @dataclass
        class TestHandles:
            client: AuthClient
            controls: dict
            actions: dict

        page._test_handles = TestHandles(
            client=client,
            controls={
                "email": email,
                "password": password,
                "toggle_mode": toggle_mode,
                "submit_btn": submit_btn,
                "messages_col": messages_col,
                "input_field": input_field,
                "send_btn": send_btn,
                "main_view": main_view,
            },
            actions={
                "submit": lambda: do_submit(None),
                "send": lambda: do_send(None),
                "start_new_chat": lambda: start_new_chat(None),
                "show_main_view": show_main_view,
                "show_auth_view": show_auth_view,
                "refresh_chats": refresh_chats,
            },
        )
    except Exception:
        pass

    # Init
    on_toggle_change(None)
    # Background session restore without blocking UI
    if _enable_auto_restore and get_refresh_token():
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







