local ok, _ = pcall(require, "dayfold_l10n")
if not ok then _ = require("gettext") end
return {
    fullname = _("Dayfold"),
    description = _([[Downloads the daily paper from your Dayfold server and opens the edition's puzzles (Sudoku, Word of the Day, Word Search and Crossword) right in the reading flow.]]),
}
