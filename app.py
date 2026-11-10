import io
import os
import shutil
import tempfile
import zipfile

import gradio as gr
import pandas as pd

from processor import process_file
from concurrent.futures import ThreadPoolExecutor

import location_store

CUSTOM_CSS = """
#file_upload .file-preview,
#file_upload ul.file-preview,
#file_upload .file-preview-holder,
#file_upload [data-testid="file"] {
    display: none !important;
}
.gr-button[disabled] {
    opacity: 0.45 !important;
    cursor: not-allowed !important;
}
"""

IS_RENDER = os.environ.get("RENDER") == "true"
location_store.init_store()


def current_df(search_text=""):
    rows = location_store.get_current_rows(search_text)
    return pd.DataFrame(rows, columns=["Account Number", "Location", "Status"])


def history_df():
    rows = location_store.get_history_rows()
    return pd.DataFrame(rows, columns=["Old Account", "Old Location", "New Account", "New Location", "Edited At"])


def on_files_change(files):
    if not files:
        return (
            gr.update(value="No files selected yet.", visible=True),
            gr.update(visible=False, open=False),
            "",
            gr.update(interactive=False),
        )
    names = [os.path.basename(f.name) for f in files]
    count = len(names)
    if count <= 5:
        listing = "\n".join(f"- {n}" for n in names)
        summary = f"**{count} file(s) selected:**\n{listing}"
        return gr.update(value=summary, visible=True), gr.update(visible=False, open=False), "", gr.update(interactive=True)
    else:
        summary = f"📁 **{count} files selected**"
        full_listing = "\n".join(f"{i+1}. {n}" for i, n in enumerate(names))
        return gr.update(value=summary, visible=True), gr.update(visible=True, open=False), full_listing, gr.update(interactive=True)


def process_files(files, session_tmp_dir):
    if session_tmp_dir and os.path.exists(session_tmp_dir):
        shutil.rmtree(session_tmp_dir, ignore_errors=True)
    if not files:
        return gr.update(value=None, visible=False), "⚠️ No files uploaded. Please upload at least one file.", session_tmp_dir

    loc_map = location_store.get_full_map()         # once, not per file
    jobs = [(os.path.basename(f.name), f.name, loc_map) for f in files]

    try:
        with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as ex:
            results = list(ex.map(lambda j: process_file(*j), jobs))
    except Exception as e:
        return gr.update(value=None, visible=False), f"⚠️ Unexpected error: {e}", session_tmp_dir

    new_tmp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(new_tmp_dir, "renamed_files.zip")
    success_log, failed_log, used_names = [], [], set()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:   # no recompression
        for f, (status, new_name, error) in zip(files, results):
            original = os.path.basename(f.name)
            base, ext = os.path.splitext(new_name)
            final, n = new_name, 1
            while final in used_names:
                final = f"{base}_{n}{ext}"; n += 1
            used_names.add(final)

            if status == "success":
                zf.write(f.name, final)
                success_log.append(f"✅ {original}  →  {final}")
            else:
                zf.write(f.name, f"FAILED_{final}")
                failed_log.append(f"❌ {original}  —  {error}")

    lines = [f"Processed {len(files)} file(s): {len(success_log)} renamed, {len(failed_log)} failed.", ""]
    return gr.update(value=zip_path, visible=True), "\n".join(lines + success_log + failed_log), new_tmp_dir


def clear_all(session_tmp_dir):
    if session_tmp_dir and os.path.exists(session_tmp_dir):
        shutil.rmtree(session_tmp_dir, ignore_errors=True)
    return (
        None,
        gr.update(value=None, visible=False),
        "",
        gr.update(value="No files selected yet.", visible=True),
        gr.update(visible=False, open=False),
        "",
        None,
        gr.update(interactive=False),
        gr.update(interactive=False),
    )


def refresh_all(search_text):
    location_store.init_store()
    return current_df(search_text), history_df(), "🔄 Refreshed."


def filter_current(search_text):
    return current_df(search_text)


def on_add_fields_change(acct, loc):
    ready = bool((acct or "").strip()) and bool((loc or "").strip())
    return gr.update(interactive=ready)


def add_mapping_ui(acct, loc, search_text):
    success, message = location_store.add_location(acct, loc) if False else location_store.add_mapping(acct, loc)
    status = f"✅ {message}" if success else f"❌ {message}"
    new_acct = "" if success else acct
    new_loc = "" if success else loc
    return status, current_df(search_text), history_df(), new_acct, new_loc, gr.update(interactive=False)


def on_row_select(df, evt: gr.SelectData):
    row = evt.index[0]
    account = str(df.iloc[row]["Account Number"])
    location = str(df.iloc[row]["Location"])
    status = str(df.iloc[row]["Status"])
    can_delete = status != "Base"
    info = f"✏️ Editing **{account}** (currently: *{location}*, {status})"
    return account, account, location, info, gr.update(interactive=can_delete), gr.update(interactive=True), gr.update(interactive=True)

def cancel_edit_ui():
    return (
        "",  # selected_account state
        "",  # new_account_input
        "",  # new_location_input
        "*No row selected — fill both fields below to add a brand-new mapping.*",  # edit_info
        gr.update(interactive=False),  # save_edit_btn
        gr.update(interactive=False),  # delete_btn
        gr.update(interactive=False),  # add_btn (fields are now empty, so disable until user types)
    )

def save_edit_ui(old_account, new_account, new_location, search_text):
    if not old_account:
        return "❌ Select a row from the table first.", current_df(search_text), history_df(), "", "", "", gr.update(interactive=False), gr.update(interactive=False)
    success, message = location_store.edit_mapping(old_account, new_account, new_location)
    status = f"✅ {message}" if success else f"❌ {message}"
    return status, current_df(search_text), history_df(), "", "", "", gr.update(interactive=False), gr.update(interactive=False)


def delete_ui(old_account, search_text):
    if not old_account:
        return "❌ Select a row from the table first.", current_df(search_text), history_df(), "", "", "", gr.update(interactive=False), gr.update(interactive=False)
    success, message = location_store.delete_mapping(old_account)
    status = f"✅ {message}" if success else f"❌ {message}"
    return status, current_df(search_text), history_df(), "", "", "", gr.update(interactive=False), gr.update(interactive=False)


with gr.Blocks(title="Excel Account Renamer", css=CUSTOM_CSS, theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        """
        # 📊 Excel / CSV Account Renamer
        Upload your Excel or CSV statement files below. Each file is scanned for its account number,
        renamed to `AccountNumber_Location.ext`, and packed into a single ZIP for download.

        🔒 **No files are stored.** Everything is processed in memory for this session only.
        """
    )

    session_tmp_dir = gr.State(value=None)
    selected_account = gr.State(value="")

    file_input = gr.File(file_count="multiple", file_types=[".xlsx", ".xls", ".xlsb", ".csv"],
                          label="Upload Excel/CSV files", elem_id="file_upload")
    file_summary = gr.Markdown(value="No files selected yet.")

    with gr.Accordion("👀 View files", open=False, visible=False) as view_files_accordion:
        view_files_list = gr.Markdown(value="")

    with gr.Row():
        process_btn = gr.Button("🚀 Process Files", variant="primary", interactive=False)
        clear_btn = gr.Button("🗑️ Clear All", interactive=False)

    output_zip = gr.File(label="Download Renamed Files (ZIP)", visible=False)
    log_output = gr.Textbox(label="Processing Log", lines=15, interactive=False)

    with gr.Accordion("⚙️ Manage Account → Location Mappings", open=False):
        storage_note = ("☁️ Changes are saved permanently to GitHub." if location_store.github_sync_enabled()
                         else "💾 Changes are saved permanently to a local file on this machine.")
        gr.Markdown(storage_note + "\n\n*Click any row below to edit or delete it. Base rows can be edited but not deleted.*")

        search_box = gr.Textbox(label="Search mappings", placeholder="Search by account number or location...")
        locations_table = gr.Dataframe(value=current_df(), headers=["Account Number", "Location", "Status"],
                                        interactive=False, wrap=True)
        refresh_btn = gr.Button("🔄 Refresh")

        gr.Markdown("**Add new / Edit selected**")
        edit_info = gr.Markdown(value="*No row selected — fill both fields below to add a brand-new mapping.*")
        with gr.Row():
            new_account_input = gr.Textbox(label="Account Number", placeholder="e.g. 925020035999999")
            new_location_input = gr.Textbox(label="Location Name", placeholder="e.g. Pune - Retailer")
        with gr.Row():
            add_btn = gr.Button("➕ Add New Mapping", interactive=False)
            save_edit_btn = gr.Button("💾 Save Edit", interactive=False)
            delete_btn = gr.Button("🗑️ Delete Selected", interactive=False)
            cancel_edit_btn = gr.Button("✖️ Cancel Edit", interactive=False)
        add_status = gr.Markdown(value="")

        gr.Markdown("**📜 Edit History**")
        history_table = gr.Dataframe(value=history_df(),
                                      headers=["Old Account", "Old Location", "New Account", "New Location", "Edited At"],
                                      interactive=False, wrap=True)

    file_input.change(fn=on_files_change, inputs=[file_input],
                       outputs=[file_summary, view_files_accordion, view_files_list, process_btn])

    process_btn.click(fn=process_files, inputs=[file_input, session_tmp_dir],
                       outputs=[output_zip, log_output, session_tmp_dir]
                       ).then(fn=lambda: gr.update(interactive=True), outputs=[clear_btn])

    clear_btn.click(fn=clear_all, inputs=[session_tmp_dir],
                     outputs=[file_input, output_zip, log_output, file_summary,
                              view_files_accordion, view_files_list, session_tmp_dir, process_btn, clear_btn])

    search_box.change(fn=filter_current, inputs=[search_box], outputs=[locations_table])
    refresh_btn.click(fn=refresh_all, inputs=[search_box], outputs=[locations_table, history_table, add_status])

    new_account_input.change(fn=on_add_fields_change, inputs=[new_account_input, new_location_input], outputs=[add_btn])
    new_location_input.change(fn=on_add_fields_change, inputs=[new_account_input, new_location_input], outputs=[add_btn])

    add_btn.click(fn=add_mapping_ui, inputs=[new_account_input, new_location_input, search_box],
                   outputs=[add_status, locations_table, history_table, new_account_input, new_location_input, add_btn])

    locations_table.select(fn=on_row_select, inputs=[locations_table],
                            outputs=[selected_account, new_account_input, new_location_input, edit_info, delete_btn, save_edit_btn, cancel_edit_btn])

    save_edit_btn.click(fn=save_edit_ui, inputs=[selected_account, new_account_input, new_location_input, search_box],
                         outputs=[add_status, locations_table, history_table, selected_account, new_account_input, new_location_input, save_edit_btn, delete_btn])

    delete_btn.click(fn=delete_ui, inputs=[selected_account, search_box],
                      outputs=[add_status, locations_table, history_table, selected_account, new_account_input, new_location_input, save_edit_btn, delete_btn])
    
    cancel_edit_btn.click(
        fn=cancel_edit_ui,
        outputs=[selected_account, new_account_input, new_location_input, edit_info, save_edit_btn, delete_btn, add_btn],
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0" if IS_RENDER else "127.0.0.1",
                server_port=int(os.environ.get("PORT", 7860)),
                inbrowser=not IS_RENDER)