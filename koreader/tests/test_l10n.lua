--[[ Checks the plugin's own catalogue: the Lua source writes English msgids and l10n/pt.po
translates them, because KOReader's gettext only knows KOReader's strings. The loader picks a
catalogue from the KOReader UI language ("pt_BR" falls back to "pt") and leaves anything it does
not know alone.

    luajit koreader/tests/test_l10n.lua
--]]

local source = debug.getinfo(1, "S").source:sub(2)
local here = source:match("^(.*)[/\\][^/\\]+$") or "."
local plugin = here .. "/../plugins/dayfold.koplugin"
package.path = plugin .. "/?.lua;" .. package.path

-- KOReader's gettext, reduced to what the plugin uses.
local gettext = setmetatable({ current_lang = "en" }, { __call = function(_, m) return m end })

table.insert(package.loaders, 1, function(name)
    if name:match("^dayfold") then return nil end  -- the plugin's own files come from disk
    if name == "gettext" then return function() return gettext end end
    return function() return {} end
end)

local _ = require("dayfold_l10n")

-- English: the message is the msgid.
assert(_("Open") == "Open", "English passes the msgid through")
assert(_("not a catalogued string") == "not a catalogued string")

-- Portuguese, from l10n/pt.po; a regional language falls back to its base.
gettext.current_lang = "pt_BR"
assert(_("Open") == "Abrir", "pt_BR uses l10n/pt.po")
assert(_("Dayfold server") == "Servidor Dayfold")
assert(_("not a catalogued string") == "not a catalogued string", "unknown msgids stay readable")

-- A language with no catalogue is English, not empty text.
gettext.current_lang = "fr"
assert(_("Open") == "Open", "unknown language falls back to the msgid")

-- KOReader's gettext can report no language: the saved UI setting is the next source.
gettext.current_lang = nil
G_reader_settings = { readSetting = function(_, k) return k == "language" and "pt" or nil end }
assert(_("Open") == "Abrir", "the saved UI language is used when gettext has none")

print("dayfold plugin l10n: ok")
