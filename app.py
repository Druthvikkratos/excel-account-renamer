import io
import os
import shutil
import tempfile
import zipfile

import gradio as gr
from processor import process_file

# CSS: hides the native uploaded-file row list inside the file_upload
# component (filenames + size + x buttons), but keeps the drag/drop
# upload zone itself visible and clickable.
CUSTOM_CSS = """
#file_upload .file-preview,
#file_upload ul.file-preview,
#file_upload .file-preview-holder,
#file_upload [data-testid="file"] {
    display: none !important;
}
"""


def on_files_change(files):
    """
    Runs every time files are added/removed.
    <=5 files -> show full names directly.
    >5 files  -> show a count + collapsible 'View files' panel.
    """
    if not files:
        return gr.update(value="No files selected yet.", visible=True), gr.update(visible=False, open=False), ""

    names = [os.path.basename(f.name) for f in files]
    count = len(names)

    if count <= 5:
        listing = "\n".join(f"- {n}" for n in names)
        summary = f"**{count} file(s) selected:**\n{listing}"
        return gr.update(value=summary, visible=True), gr.update(visible=False, open=False), ""
    else:
        summary = f"📁 **{count} files selected**"
        full_listing = "\n".join(f"{i+1}. {n}" for i, n in enumerate(names))
        return gr.update(value=summary, visible=True), gr.update(visible=True, open=False), full_listing


def process_files(files, session_tmp_dir):
    """
    session_tmp_dir is private to this browser session (via gr.State),
    so one user's cleanup/zip creation can never touch another user's files.
    """
    # clean up this session's own previous temp dir, not a global/shared one
    if session_tmp_dir and os.path.exists(session_tmp_dir):
        shutil.rmtree(session_tmp_dir, ignore_errors=True)

    if not files:
        return (
            gr.update(value=None, visible=False),
            "⚠️ No files uploaded. Please upload at least one file.",
            session_tmp_dir,
        )

    success_log = []
    failed_log = []
    used_names = set()

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_obj in files:
            original_name = os.path.basename(file_obj.name)
            with open(file_obj.name, "rb") as f:
                file_bytes = f.read()

            status, new_name, out_bytes, error = process_file(original_name, file_bytes)

            # avoid overwriting if two files resolve to the same new name
            final_name = new_name
            counter = 1
            base, ext = os.path.splitext(new_name)
            while final_name in used_names:
                final_name = f"{base}_{counter}{ext}"
                counter += 1
            used_names.add(final_name)

            if status == "success":
                zf.writestr(final_name, out_bytes)
                success_log.append(f"✅ {original_name}  →  {final_name}")
            else:
                zf.writestr(f"FAILED_{final_name}", out_bytes)
                failed_log.append(f"❌ {original_name}  —  {error}")

    zip_buffer.seek(0)

    # fresh temp dir for THIS session/run only
    new_tmp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(new_tmp_dir, "renamed_files.zip")
    with open(zip_path, "wb") as f:
        f.write(zip_buffer.getvalue())

    summary_lines = [f"Processed {len(files)} file(s): {len(success_log)} renamed, {len(failed_log)} failed.", ""]
    summary_lines += success_log
    summary_lines += failed_log
    summary = "\n".join(summary_lines)

    return gr.update(value=zip_path, visible=True), summary, new_tmp_dir


def clear_all(session_tmp_dir):
    if session_tmp_dir and os.path.exists(session_tmp_dir):
        shutil.rmtree(session_tmp_dir, ignore_errors=True)
    return (
        None,                                                        # file_input
        gr.update(value=None, visible=False),                        # output_zip
        "",                                                           # log_output
        gr.update(value="No files selected yet.", visible=True),     # file_summary
        gr.update(visible=False, open=False),                        # view_files_accordion
        "",                                                           # view_files_list
        None,                                                         # session_tmp_dir reset
    )


with gr.Blocks(title="Excel Account Renamer", css=CUSTOM_CSS) as demo:
    gr.Markdown(
        """
        # 📊 Excel / CSV Account Renamer
        Upload your Excel or CSV statement files below.
        Each file is scanned for its account number, renamed to
        `AccountNumber_Location.ext`, and packed into a single ZIP for download.

        🔒 **No files are stored.** Everything is processed in memory for this
        session only and cleared automatically when you click **Clear All** or reload the page.
        """
    )

    # Private per-user state — isolates each browser session's temp folder
    # from every other concurrent user. Not shared, not global.
    session_tmp_dir = gr.State(value=None)

    file_input = gr.File(
        file_count="multiple",
        file_types=[".xlsx", ".xls", ".xlsb", ".csv"],
        label="Upload Excel/CSV files",
        elem_id="file_upload",
    )

    file_summary = gr.Markdown(value="No files selected yet.")

    with gr.Accordion("👀 View files", open=False, visible=False) as view_files_accordion:
        view_files_list = gr.Markdown(value="")

    with gr.Row():
        process_btn = gr.Button("🚀 Process Files", variant="primary")
        clear_btn = gr.Button("🗑️ Clear All")

    output_zip = gr.File(label="Download Renamed Files (ZIP)", visible=False)
    log_output = gr.Textbox(label="Processing Log", lines=15, interactive=False)

    file_input.change(
        fn=on_files_change,
        inputs=[file_input],
        outputs=[file_summary, view_files_accordion, view_files_list],
    )

    process_btn.click(
        fn=process_files,
        inputs=[file_input, session_tmp_dir],
        outputs=[output_zip, log_output, session_tmp_dir],
    )

    clear_btn.click(
        fn=clear_all,
        inputs=[session_tmp_dir],
        outputs=[
            file_input,
            output_zip,
            log_output,
            file_summary,
            view_files_accordion,
            view_files_list,
            session_tmp_dir,
        ],
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)))