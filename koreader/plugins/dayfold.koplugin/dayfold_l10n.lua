--[[--
Translations for the Dayfold plugin.

Messages are written in English (the msgid). KOReader's own catalog only knows KOReader's
strings, so the plugin ships its catalogs in l10n/<lang>.po and picks one from the KOReader
UI language (Settings › Language): "pt_BR" tries l10n/pt_BR.po, then l10n/pt.po. Anything
not found there goes through KOReader's gettext, and English is the final fallback.

Usage: local _ = require("dayfold_l10n")
--]]--

local gettext = require("gettext")

local dir = (debug.getinfo(1, "S").source or ""):match("^@(.*)/[^/]*$") or "."

local function unescape(s)
    return (s:gsub("\\(.)", { n = "\n", t = "\t", ['"'] = '"', ["\\"] = "\\" }))
end

-- Minimal .po reader: msgid/msgstr pairs with continuation lines. No plurals or contexts.
local function readPo(path)
    local f = io.open(path, "r")
    if not f then return nil end
    local catalog, msgid, msgstr, field = {}, nil, nil, nil
    local function flush()
        if msgid and msgid ~= "" and msgstr and msgstr ~= "" then catalog[msgid] = msgstr end
        msgid, msgstr, field = nil, nil, nil
    end
    for line in f:lines() do
        local key, text = line:match('^(msg%a+)%s+"(.*)"%s*$')
        if key == "msgid" then
            flush()
            msgid, field = unescape(text), "msgid"
        elseif key == "msgstr" then
            msgstr, field = unescape(text), "msgstr"
        else
            local cont = line:match('^%s*"(.*)"%s*$')
            if cont and field == "msgid" then msgid = msgid .. unescape(cont)
            elseif cont and field == "msgstr" then msgstr = msgstr .. unescape(cont)
            elseif not cont then field = nil end
        end
    end
    flush()
    f:close()
    return catalog
end

local function uiLanguage()
    -- the language KOReader's own gettext is using, else the saved UI setting
    local lang = type(gettext) == "table" and gettext.current_lang
    if not lang and G_reader_settings then lang = G_reader_settings:readSetting("language") end
    return lang or "en"
end

local loaded_for, catalog

local function currentCatalog()
    local lang = uiLanguage()
    if lang ~= loaded_for then
        loaded_for, catalog = lang, nil
        local code = lang:match("^([%a_]+)") or "en"
        for _, name in ipairs({ code, code:match("^(%a%a)") }) do
            catalog = catalog or readPo(dir .. "/l10n/" .. name .. ".po")
        end
    end
    return catalog
end

return function(msgid)
    local c = currentCatalog()
    return (c and c[msgid]) or gettext(msgid)
end
