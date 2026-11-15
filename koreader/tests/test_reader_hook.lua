--[[ Checks the reader integration: KOReader keeps its own end-of-book action, and Dayfold only
takes over while a Dayfold edition is the open document.

KOReader is not available here, so every module the plugin requires is stubbed — enough to load
the plugin's files, nothing more. The plugin's own modules still load from disk.

    luajit koreader/tests/test_reader_hook.lua
--]]

local source = debug.getinfo(1, "S").source:sub(2)
local here = source:match("^(.*)[/\\][^/\\]+$") or "."
local plugin = here .. "/../plugins/dayfold.koplugin"
package.path = plugin .. "/?.lua;" .. package.path

local function stub()
    local m = {}
    function m.extend(self, t)
        t = t or {}
        t.__index = t
        return setmetatable(t, { __index = self })
    end
    -- Permissive: any member is a no-op function, and the module itself is callable like
    -- KOReader's gettext (which returns the source string when it has no translation).
    return setmetatable(m, {
        __index = function() return function() return nil end end,
        __call = function(_, msgid) return msgid end,
    })
end

local gettext = setmetatable({ current_lang = "en" }, { __call = function(_, m) return m end })

table.insert(package.loaders, 1, function(name)
    if name:match("^dayfold") then return nil end  -- the plugin's own files come from disk
    if name == "gettext" then return function() return gettext end end
    return function() return stub() end
end)

G_reader_settings = { readSetting = function() return nil end }

local Dayfold = dofile(plugin .. "/main.lua")

-- A plugin instance, as KOReader builds it: the class provides isEdition/onEditionEnd.
local reader = setmetatable({ config = {}, settings = {}, ui = {} }, { __index = Dayfold })
local original = 0
reader.ui.status = { onEndOfBook = function() original = original + 1; return "ko-reader" end }
reader.ui.document = { file = "/mnt/us/documents/Dayfold/dayfold-2026-11-15-0001.epub" }
Dayfold.hookReader(reader)

assert(reader.ui.status.onEndOfBook(reader.ui.status) == true, "edition: Dayfold takes over")
assert(original == 0, "edition: KOReader's handler must not run")

reader.ui.document.file = "/mnt/us/documents/novel.epub"
assert(reader.ui.status.onEndOfBook(reader.ui.status) == "ko-reader", "other book: KOReader's handler")
assert(original == 1, "other book: handler ran once")

-- Hooking again must not stack wrappers or lose the original.
Dayfold.hookReader(reader)
reader.ui.document.file = "/mnt/us/documents/Dayfold/dayfold-2026-11-16-0001.epub"
assert(reader.ui.status.onEndOfBook(reader.ui.status) == true, "second edition: Dayfold takes over")
reader.ui.document.file = "/mnt/us/documents/other.epub"
assert(reader.ui.status.onEndOfBook(reader.ui.status) == "ko-reader" and original == 2,
    "single wrapper, original intact")

print("dayfold plugin reader hook: ok")
