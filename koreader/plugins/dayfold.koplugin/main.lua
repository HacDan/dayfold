--[[--
Dayfold for KOReader.

* Downloads the latest edition (EPUB + games.json) from a Dayfold server.
* While reading a Dayfold edition: links "dayfold://game/N" open the interactive game
  and reaching the end of the edition offers the games, so reading flows from the news
  to the cartoon and the puzzles like turning the pages of a paper.
* Game progress is saved per edition.

@module koplugin.Dayfold
--]]--

local ButtonDialog = require("ui/widget/buttondialog")
local ConfirmBox = require("ui/widget/confirmbox")
local DataStorage = require("datastorage")
local Device = require("device")
local InfoMessage = require("ui/widget/infomessage")
local JSON = require("json")
local LuaSettings = require("luasettings")
local MultiInputDialog = require("ui/widget/multiinputdialog")
local NetworkMgr = require("ui/network/manager")
local UIManager = require("ui/uimanager")
local WidgetContainer = require("ui/widget/container/widgetcontainer")
local ffiUtil = require("ffi/util")
local http = require("socket.http")
local lfs = require("libs/libkoreader-lfs")
local logger = require("logger")
local ltn12 = require("ltn12")
local socket = require("socket")
local socketutil = require("socketutil")
local util = require("util")
local _ = require("dayfold_l10n")

local GAMES = {
    sudoku = require("dayfold_games/sudoku"),
    wordle = require("dayfold_games/wordle"),
    wordsearch = require("dayfold_games/wordsearch"),
    crossword = require("dayfold_games/crossword"),
}

local Dayfold = WidgetContainer:extend{
    name = "dayfold",
    is_doc_only = false,
}

-- ------------------------------------------------------------------ config

function Dayfold:loadConfig()
    local cfg = {}
    local file = self.path .. "/dayfold_config.lua"
    if lfs.attributes(file, "mode") == "file" then
        local ok, data = pcall(dofile, file)
        if ok and type(data) == "table" then cfg = data else logger.warn("Dayfold: invalid config", data) end
    end
    local saved = self.settings:readSetting("server_config") or {}
    for k, v in pairs(saved) do cfg[k] = v end
    cfg.keep = tonumber(cfg.keep) or 7
    if not cfg.folder then
        local home = G_reader_settings:readSetting("home_dir")
        if not home then home = Device:isKindle() and "/mnt/us/documents" or DataStorage:getDataDir() end
        cfg.folder = home .. "/Dayfold"
    end
    if cfg.server then cfg.server = cfg.server:gsub("/+$", "") end
    self.config = cfg
end

function Dayfold:init()
    self.settings = LuaSettings:open(DataStorage:getSettingsDir() .. "/dayfold.lua")
    self:loadConfig()
    self.ui.menu:registerToMainMenu(self)
    if self.ui.document and self:isEdition(self.ui.document.file) then
        -- Solutions and pocket-guess pages are non-linear: keep them out of the page flow,
        -- reachable by links only, so the edition ends on the masthead page (no spoilers).
        if self.ui.doc_settings and not self.ui.doc_settings:has("hide_nonlinear_flows") then
            self.ui.doc_settings:saveSetting("hide_nonlinear_flows", true)
        end
        self:hookReader()
    elseif not self.ui.document then
        -- File manager: fetch today's edition quietly if Wi-Fi is already on.
        UIManager:scheduleIn(3, function() self:autoSync() end)
    end
end

-- Waking the device up is a good moment to look for a new edition (only if Wi-Fi is on).
function Dayfold:onResume()
    UIManager:scheduleIn(15, function() self:autoSync() end)
end

-- ------------------------------------------------------------------ helpers

function Dayfold:isEdition(path)
    return type(path) == "string" and path:match("dayfold%-%d%d%d%d%-%d%d%-%d%d[%-%d]*%.epub$") ~= nil
end

local function gamesPath(epub)
    return (epub:gsub("%.epub$", ".games.json"))
end

local function readFile(path)
    local f = io.open(path, "rb")
    if not f then return nil end
    local data = f:read("*a")
    f:close()
    return data
end

function Dayfold:loadGames(epub)
    local raw = readFile(gamesPath(epub))
    if not raw then return nil end
    local ok, data = pcall(JSON.decode, raw)
    if ok and type(data) == "table" then return data end
    return nil
end

function Dayfold:localEditions()
    local list = {}
    if lfs.attributes(self.config.folder, "mode") ~= "directory" then return list end
    for name in lfs.dir(self.config.folder) do
        if name:match("^dayfold%-%d%d%d%d%-%d%d%-%d%d[%-%d]*%.epub$") then
            table.insert(list, self.config.folder .. "/" .. name)
        end
    end
    table.sort(list, function(a, b) return a > b end)
    return list
end

function Dayfold:request(url, filepath)
    local sink = {}
    local req = { url = url, method = "GET", headers = { ["X-Dayfold-Token"] = self.config.token or "" } }
    if filepath then
        req.sink = ltn12.sink.file(io.open(filepath, "wb"))
        socketutil:set_timeout(socketutil.FILE_BLOCK_TIMEOUT, socketutil.FILE_TOTAL_TIMEOUT * 3)
    else
        req.sink = ltn12.sink.table(sink)
        socketutil:set_timeout(socketutil.LARGE_BLOCK_TIMEOUT, socketutil.LARGE_TOTAL_TIMEOUT)
    end
    local code, headers, status = socket.skip(1, http.request(req))
    socketutil:reset_timeout()
    if headers == nil then return false, string.format(_("network unavailable (%s)"), tostring(status or code)) end
    if code ~= 200 then
        if filepath then os.remove(filepath) end
        if code == 401 then return false, _("invalid token") end
        if code == 404 then return false, _("no edition ready on the server") end
        return false, "HTTP " .. tostring(code)
    end
    return true, filepath or table.concat(sink)
end

-- ------------------------------------------------------------------ sleep screen

-- Folder holding only the latest front page. KOReader's "random image" sleep screen points
-- here, and on a Kindle the optional watcher (kindle/dayfold-screensaver.sh) draws the same file
-- over the stock screensaver.
function Dayfold:screensaverDir()
    if Device:isKindle() then return "/mnt/us/dayfold/screensaver" end
    return DataStorage:getDataDir() .. "/dayfold-screensaver"
end

function Dayfold:applyScreensaver(enabled, cover_url)
    local dir = self:screensaverDir()
    local file = dir .. "/cover.png"
    if enabled then
        util.makePath(dir)
        if cover_url then
            local ok = self:request(cover_url, file .. ".part")
            if ok then os.rename(file .. ".part", file) end
        end
        if lfs.attributes(file, "mode") ~= "file" then return end
        if self.settings:readSetting("previous_screensaver") == nil then
            self.settings:saveSetting("previous_screensaver", {
                type = G_reader_settings:readSetting("screensaver_type") or false,
                dir = G_reader_settings:readSetting("screensaver_dir") or false,
                message = G_reader_settings:readSetting("screensaver_show_message") or false,
            })
        end
        G_reader_settings:saveSetting("screensaver_type", "random_image")
        G_reader_settings:saveSetting("screensaver_dir", dir)
        G_reader_settings:saveSetting("screensaver_show_message", false) -- the front page speaks for itself
    else
        os.remove(file)
        local prev = self.settings:readSetting("previous_screensaver")
        if prev then
            if prev.type then G_reader_settings:saveSetting("screensaver_type", prev.type)
            else G_reader_settings:delSetting("screensaver_type") end
            if prev.dir then G_reader_settings:saveSetting("screensaver_dir", prev.dir)
            else G_reader_settings:delSetting("screensaver_dir") end
            G_reader_settings:saveSetting("screensaver_show_message", prev.message == true)
            self.settings:delSetting("previous_screensaver")
        end
    end
    self.settings:saveSetting("screensaver_enabled", enabled)
    self.settings:flush()
end

-- ------------------------------------------------------------------ sync

function Dayfold:sync(interactive)
    if not self.config.server or not self.config.token then
        if interactive then self:configure() end
        return
    end
    local run = function()
        local ok, body = self:request(self.config.server .. "/feed/latest.json")
        if not ok then
            if interactive then UIManager:show(InfoMessage:new{ text = "Dayfold: " .. body }) end
            return
        end
        local okj, meta = pcall(JSON.decode, body)
        if not okj or type(meta) ~= "table" or not meta.epub_name then
            if interactive then UIManager:show(InfoMessage:new{ text = _("Dayfold: invalid response from the server") }) end
            return
        end
        lfs.mkdir(self.config.folder)
        local dest = self.config.folder .. "/" .. meta.epub_name
        local same = lfs.attributes(dest, "mode") == "file"
        if not same then
            local tmp = dest .. ".part"
            local okd, err = self:request(self.config.server .. meta.epub, tmp)
            if not okd then
                if interactive then UIManager:show(InfoMessage:new{ text = "Dayfold: " .. err }) end
                return
            end
            os.rename(tmp, dest)
        end
        self:request(self.config.server .. meta.games, gamesPath(dest))
        local ok_ss, err_ss = pcall(self.applyScreensaver, self, meta.screensaver == true,
            self.config.server .. (meta.cover or "/feed/latest.cover.png"))
        if not ok_ss then logger.warn("Dayfold: sleep screen", err_ss) end
        self.settings:saveSetting("last_sync", os.date("%Y-%m-%d"))
        self.settings:saveSetting("last_edition", meta.id)
        self.settings:flush()
        self:prune()
        if same and not interactive then return end
        UIManager:show(ConfirmBox:new{
            text = string.format(_("%s No. %s (%s) is ready.\n\n%s\n\nOpen it now?"), meta.title or "Dayfold",
                tostring(meta.number or ""), meta.date or "", meta.headline or ""),
            ok_text = _("Open"),
            ok_callback = function() self:open(dest) end,
        })
    end
    if interactive then
        NetworkMgr:runWhenOnline(function()
            UIManager:show(InfoMessage:new{ text = _("Downloading today's edition…"), timeout = 1 })
            UIManager:scheduleIn(0.5, run)
        end)
    else
        run()
    end
end

function Dayfold:autoSync()
    if self.settings:readSetting("auto_sync") == false then return end
    if not (self.config.server and self.config.token) then return end
    -- cheap: one small JSON request; the EPUB is only fetched when the edition id changed
    if NetworkMgr:isOnline() then
        local ok, err = pcall(self.sync, self, false)
        if not ok then logger.warn("Dayfold auto sync failed", err) end
    end
end

function Dayfold:prune()
    local list = self:localEditions()
    for i = self.config.keep + 1, #list do
        local epub = list[i]
        os.remove(epub)
        os.remove(gamesPath(epub))
        local sdr = epub:gsub("%.epub$", ".sdr")
        if lfs.attributes(sdr, "mode") == "directory" then ffiUtil.purgeDir(sdr) end
    end
end

function Dayfold:open(path)
    if self.ui.document then
        self.ui:switchDocument(path)
    else
        local ReaderUI = require("apps/reader/readerui")
        ReaderUI:showReader(path)
    end
end

function Dayfold:openLatest()
    local list = self:localEditions()
    if #list == 0 then
        UIManager:show(ConfirmBox:new{
            text = _("No edition on this device. Download one now?"),
            ok_callback = function() self:sync(true) end,
        })
        return
    end
    self:open(list[1])
end

function Dayfold:configure()
    local dialog
    dialog = MultiInputDialog:new{
        title = _("Dayfold server"),
        fields = {
            { text = self.config.server or "", hint = "http://192.168.0.10:8422", description = _("Server address") },
            { text = self.config.token or "", hint = "token", description = _("Feed token (dashboard › Kindle)") },
        },
        buttons = { {
            { text = _("Cancel"), id = "close", callback = function() UIManager:close(dialog) end },
            { text = _("Save"), is_enter_default = true, callback = function()
                local f = dialog:getFields()
                self.settings:saveSetting("server_config", { server = f[1], token = f[2] })
                self.settings:flush()
                UIManager:close(dialog)
                self:loadConfig()
                UIManager:show(InfoMessage:new{ text = _("Server saved."), timeout = 2 })
            end },
        } },
    }
    UIManager:show(dialog)
    dialog:onShowKeyboard()
end

-- ------------------------------------------------------------------ games

function Dayfold:stateKey(data, index)
    return (data.edition or "edition") .. ":" .. tostring(index)
end

function Dayfold:openGame(epub, index, on_close)
    local data = self:loadGames(epub)
    if not data or not data.games then
        UIManager:show(InfoMessage:new{ text = _("The puzzles of this edition were not downloaded. Sync again.") })
        return
    end
    local game
    for _, g in ipairs(data.games) do
        if tonumber(g.index) == tonumber(index) then game = g end
    end
    local Widget = game and GAMES[game.kind]
    if not Widget then
        UIManager:show(InfoMessage:new{ text = _("Puzzle not found.") })
        return
    end
    local key = self:stateKey(data, index)
    local states = self.settings:readSetting("games") or {}
    local widget = Widget:new{
        game = game,
        edition_title = (data.title or "Dayfold") .. " · " .. (data.date or ""),
        state = states[key] or {},
        on_save = function(state)
            local all = self.settings:readSetting("games") or {}
            all[key] = state
            self.settings:saveSetting("games", all)
            self.settings:flush()
        end,
        on_close = on_close,
    }
    UIManager:show(widget, "full")
end

function Dayfold:gameDone(data, g)
    local st = (self.settings:readSetting("games") or {})[self:stateKey(data, g.index)]
    if not st then return false end
    if g.kind == "wordle" then
        local guesses = st.guesses or {}
        return guesses[#guesses] == g.solution.answer
    elseif g.kind == "wordsearch" then
        local n = 0
        for _ in pairs(st.found or {}) do n = n + 1 end
        return n == #g.puzzle.words
    end
    return st.done == true
end

function Dayfold:showGames(epub, title)
    local data = self:loadGames(epub)
    if not data or not data.games or #data.games == 0 then
        UIManager:show(InfoMessage:new{ text = _("This edition has no puzzles.") })
        return
    end
    local dialog
    local buttons = {}
    for _, g in ipairs(data.games) do
        table.insert(buttons, { {
            text = (self:gameDone(data, g) and "✓ " or "") .. g.title,
            callback = function()
                UIManager:close(dialog)
                self:openGame(epub, g.index, function() self:showGames(epub, title) end)
            end,
        } })
    end
    table.insert(buttons, { { text = _("Back to the paper"), callback = function() UIManager:close(dialog) end } })
    dialog = ButtonDialog:new{ title = title or _("Puzzles"), title_align = "center", buttons = buttons }
    UIManager:show(dialog)
end

-- ------------------------------------------------------------------ reader integration

function Dayfold:hookReader()
    local plugin = self
    local link = self.ui.link
    if link and not link._dayfold_hooked then
        link._dayfold_hooked = true
        local orig = link.onGotoLink
        link.onGotoLink = function(this, l, ...)
            local url = l and (l.xpointer or l.uri)
            if type(url) == "string" then
                local idx = url:match("^dayfold://game/(%d+)")
                if idx then
                    plugin:openGame(plugin.ui.document.file, tonumber(idx))
                    return true
                end
            end
            return orig(this, l, ...)
        end
    end
    local status = self.ui.status
    if status and not status._dayfold_hooked then
        status._dayfold_hooked = true
        status.onEndOfBook = function()
            plugin:onEditionEnd()
            return true
        end
    end
end

function Dayfold:onEditionEnd()
    local epub = self.ui.document.file
    local dialog
    local buttons = {
        { { text = _("Play the puzzles"), callback = function() UIManager:close(dialog); self:showGames(epub) end } },
        { { text = _("Back to the front page"), callback = function()
            UIManager:close(dialog)
            self.ui:handleEvent(require("ui/event"):new("GotoPage", 1))
        end } },
        { { text = _("Look for a new edition"), callback = function() UIManager:close(dialog); self:sync(true) end } },
        { { text = _("Library"), callback = function() UIManager:close(dialog); self.ui:onClose(); require("apps/filemanager/filemanager"):showFiles(self.config.folder) end } },
        { { text = _("Keep reading"), callback = function() UIManager:close(dialog) end } },
    }
    dialog = ButtonDialog:new{ title = _("End of edition"), title_align = "center", buttons = buttons }
    UIManager:show(dialog)
end

-- ------------------------------------------------------------------ menu

function Dayfold:addToMainMenu(menu_items)
    menu_items.dayfold = {
        text = _("Dayfold"),
        sorting_hint = "tools",
        sub_item_table = {
            { text = _("Download today's edition"), callback = function() self:sync(true) end },
            { text = _("Open latest edition"), callback = function() self:openLatest() end },
            {
                text = _("Puzzles of this edition"),
                enabled_func = function() return #self:localEditions() > 0 end,
                callback = function()
                    local current = self.ui.document and self:isEdition(self.ui.document.file) and self.ui.document.file
                    self:showGames(current or self:localEditions()[1])
                end,
            },
            {
                text = _("Download automatically (when Wi-Fi is already on)"),
                checked_func = function() return self.settings:readSetting("auto_sync") ~= false end,
                callback = function()
                    self.settings:saveSetting("auto_sync", self.settings:readSetting("auto_sync") == false)
                    self.settings:flush()
                end,
                separator = true,
            },
            { text = _("Set up server"), keep_menu_open = true, callback = function() self:configure() end },
            {
                text_func = function()
                    return string.format(_("Last sync: %s"), self.settings:readSetting("last_sync") or _("never"))
                end,
                enabled = false,
            },
        },
    }
end

return Dayfold
