# F.R.I.D.A.Y. 3.0 — File Operations & Automation Agent Audit

**Subsystem**: File Operations & Autonomous File Organizer (`friday_core/skills/builtins/file_ops.py`, `friday_ui/core/engine.py`)  
**Audit Scope**: File search execution, semantic natural language file selection, direct file creation on disk, and dry-run preview organization.

---

## 1. Discovered Vulnerabilities & Architecture Overhaul

Prior to this engineering phase, file operations suffered from four critical bugs:
1. **Search Instruction Hallucination (BUG-016)**: No file search tool was registered. Queries like `"find all PDF files in Downloads"` triggered LLM text generation explaining how to use PowerShell `Get-ChildItem`.
2. **Literal Filename Misinterpretation (BUG-017)**: Queries like `"open the first PDF file in my Downloads folder"` treated the phrase `"first PDF file in my Downloads"` as a literal filename string, failing to find or open any files.
3. **Runaway Notepad Launch on File Creation (BUG-012)**: Asking to create a text file on the desktop misclassified into `APP_LAUNCH`, triggering an unbounded loop of Notepad windows.
4. **Mutating Organization without Preview**: Asking to scan or preview organization opened File Explorer or risked modifying directory contents without user confirmation.

---

## 2. Implemented Verifiable Skills

### A. FileSearchSkill (`file_search`)
- **Schema**:
  - Input: `location` / `folder`, `pattern` / `query`, `file_type`, `recursive`, `max_results`
  - Output: `success`, `folder`, `pattern`, `count`, `files` (with `name`, `path`, `size_bytes`, `mtime`)
- **Folder Resolution**:
  - `resolve_folder()` checks absolute directory paths first, then standard user libraries (`Downloads`, `Desktop`, `Documents`, `Pictures`, `Music`, `Videos`) with automatic OneDrive fallback.
- **Verification**: Asserts filesystem access and returns structured file metadata. Tested and verified on live Windows filesystem.

### B. FileSelectorSkill (`file_select`)
- **Schema**:
  - Input: `location` / `folder`, `file_type`, `selector` / `order`, `filter_contains`, `action` (`open` or `select`)
  - Output: `success`, `selected_file`, `file_name`, `filename`, `action_taken`, `message`
- **Semantic Selectors Supported**:
  - `first` / `1st`: Alphabetical ordering by name.
  - `latest` / `newest` / `most recent`: Most recently modified file (`mtime` descending).
  - `oldest`: Oldest file by modification time (`mtime` ascending).
  - `largest` / `biggest`: Largest file by byte size (`size` descending).
  - `smallest`: Smallest file by byte size (`size` ascending).
  - `second` / `2nd`: Second file in deterministic sort.
  - `third` / `3rd`: Third file in deterministic sort.
- **Execution & Action**: Launches target file using native OS shell association (`os.startfile` on Windows).
- **Postcondition**: Verifies the selected file path exists on disk prior to and after launch.

### C. CreateFileSkill (`create_file`)
- **Schema**:
  - Input: `file_name`, `directory` / `folder`, `content`, `encoding`, `overwrite`
  - Output: `success`, `path`, `size_bytes`, `message`
- **Zero Notepad Dependency**: Writes file directly to disk via atomic Python I/O, bypassing GUI text editors entirely.
- **Postcondition**: Independent readback verifies file existence on disk, file size > 0, and exact content match.

### D. Autonomous File Organizer Dry-Run Preview
- **Implementation**: `organize_directory(folder_keyword, dry_run=True)`
- **Behavior**:
  - Scans loose files in target directory.
  - Categorizes files into standardized folders (`Documents/`, `Images/`, `Archives/`, `Code/`, `Media/`, `Installers/`, `PowerPoint/`, `Word/`, `Excel/`).
  - Protects sensitive directories (`jarvis voice`, `Rainmeter`, `Arduino`, `GitHub`, etc.).
  - When `dry_run=True`: Generates structured markdown summary of files and proposed destinations. **Zero files are moved, zero directories are created.**
  - Prevents opening File Explorer on read-only preview requests.
