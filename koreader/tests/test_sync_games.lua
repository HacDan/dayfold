--[[ Checks the games.json handling in Dayfold:sync: a failed puzzle download must never leave a
stale or truncated games.json next to the edition, and a good one must replace it in one step.

KOReader is not available here; the modules the plugin requires are stubbed, but files, the
download sink and the HTTP client behave for real against a temporary folder.

    luajit koreader/tests/test_sync_games.lua
--]]

local source = debug.getinfo(1, "S").source:sub(2)
local here = source:match("^(.*)[/\\][^/\\]+$") or "."
local plugin = here .. "/../plugins/dayfold.koplugin"
package.path = plugin .. "/?.lua;" .. package.path

local REAL = {}

-- KOReader's gettext, reduced to what the plugin uses: a callable module with the current UI
-- language, so l10n/pt.po is read for a Portuguese device and msgids pass through otherwise.
REAL["gettext"] = setmetatable({ current_lang = "en" }, { __call = function(_, m) return m end })

local function stub()
    local m = {}
    function m.extend(self, t)
        t = t or {}
        t.__index = t
        return setmetatable(t, { __index = self })
    end
    return setmetatable(m, { __index = function() return function() return nil end end,
                             __call = function(_, s) return s end })
end

table.insert(package.loaders, 1, function(name)
    if name:match("^dayfold") then return nil end
    if REAL[name] then return function() return REAL[name] end end
    return function() return stub() end
end)

local function read(path)
    local f = io.open(path, "rb")
    if not f then return nil end
    local data = f:read("*a")
    f:close()
    return data
end

local function write(path, data)
    local f = assert(io.open(path, "wb"))
    f:write(data)
    f:close()
end

-- Files on disk, downloads into the sink, failures on demand.
REAL["libs/libkoreader-lfs"] = {
    attributes = function(path) return read(path) and "file" or nil end,
    mkdir = function(path) os.execute("mkdir -p '" .. path .. "'") return true end,
}
REAL["ltn12"] = { sink = {
    file = function(f) return function(chunk)
        if chunk then return f:write(chunk) and 1 or nil end
        f:close()
        return 1
    end end,
    table = function(t) return function(chunk) if chunk then t[#t + 1] = chunk end return 1 end end,
} }
REAL["socket"] = { skip = function(_, a, b, c) return a, b, c end }
REAL["socketutil"] = {
    set_timeout = function() end, reset_timeout = function() end,
    FILE_BLOCK_TIMEOUT = 1, FILE_TOTAL_TIMEOUT = 1, LARGE_BLOCK_TIMEOUT = 1, LARGE_TOTAL_TIMEOUT = 1,
}

local state = { meta = nil, bodies = {}, fail = nil }
REAL["json"] = { decode = function() return state.meta end }
REAL["socket.http"] = { request = function(req)
    if state.fail and req.url:find(state.fail, 1, true) then return 1, nil, "connection reset" end
    local body = state.bodies[req.url]
    if body == nil then return 404, {}, "HTTP/1.1 404 Not Found" end
    if req.sink then
        req.sink(body)
        req.sink(nil)  -- end of stream: socket.http closes the sink like this at EOF
    end
    return 200, {}, "HTTP/1.1 200 OK"
end }

G_reader_settings = { readSetting = function() return nil end }

local Dayfold = dofile(plugin .. "/main.lua")

local dir = os.tmpname()
os.remove(dir)
os.execute("mkdir -p '" .. dir .. "'")
local function at(name) return dir .. "/" .. name end

local store = {}
local settings = {
    readSetting = function(_, key) return store[key] end,
    saveSetting = function(_, key, value) store[key] = value end,
    flush = function() end,
}

local reader = setmetatable({
    config = { server = "http://server", token = "token", folder = dir, keep = 7 },
    settings = settings,
    ui = {},
}, { __index = Dayfold })

local function sync(meta, bodies, fail)
    state.meta, state.bodies, state.fail = meta, bodies, fail
    reader:sync(false)  -- non-interactive: no dialogs, no network checks
end

-- 1. The edition is already on the device and the puzzle download fails: the good games.json
--    stays exactly as it was (the sink must not have truncated it) and no .part is left behind.
local epub = "dayfold-2026-11-15-0001.epub"
write(at(epub), "paper")
write(at("dayfold-2026-11-15-0001.games.json"), "old games")
local meta = { id = "e1", rev = 1700000000, epub_name = epub,
               epub = "/feed/latest.epub", games = "/feed/latest.games.json" }
store.last_edition, store.last_rev = meta.id, meta.rev
sync(meta, { ["http://server/feed/latest.json"] = "{}" }, "/feed/latest.games.json")

assert(read(at("dayfold-2026-11-15-0001.games.json")) == "old games", "older games.json must survive intact")
assert(read(at("dayfold-2026-11-15-0001.games.json.part")) == nil, "no .part left behind")

-- 2. A new edition downloads but its puzzles fail: it must not appear with games at all.
local next_epub = "dayfold-2026-11-16-0001.epub"
sync({ id = "e2", epub_name = next_epub, epub = "/feed/latest.epub", games = "/feed/latest.games.json" },
    { ["http://server/feed/latest.json"] = "{}", ["http://server/feed/latest.epub"] = "new paper" },
    "/feed/latest.games.json")

assert(read(at(next_epub)) == "new paper", "the paper itself downloaded")
assert(read(at("dayfold-2026-11-16-0001.games.json")) == nil, "failed games download leaves no games.json")
assert(read(at("dayfold-2026-11-16-0001.games.json.part")) == nil, "no .part left behind")

-- 3. A good download replaces the file in one step.
store.last_edition, store.last_rev = meta.id, meta.rev
sync(meta, { ["http://server/feed/latest.json"] = "{}",
             ["http://server/feed/latest.games.json"] = "new games" }, nil)
assert(read(at("dayfold-2026-11-15-0001.games.json")) == "new games", "good download replaces the games")
assert(read(at("dayfold-2026-11-15-0001.games.json.part")) == nil, "no .part left behind")

-- 4. Same edition and same revision: the copy on the device is current, nothing is fetched.
write(at(epub), "paper v1")
store.last_edition, store.last_rev = "e1", 1700000000
sync({ id = "e1", rev = 1700000000, epub_name = epub,
       epub = "/feed/latest.epub", games = "/feed/latest.games.json" },
    { ["http://server/feed/latest.json"] = "{}",
      ["http://server/feed/latest.epub"] = "must not be downloaded" }, nil)
assert(read(at(epub)) == "paper v1", "same id and revision: the paper is not fetched again")

-- 5. Re-typeset on the server: same id and file name, new revision → fetch the paper again.
sync({ id = "e1", rev = 1700000600, epub_name = epub,
       epub = "/feed/latest.epub", games = "/feed/latest.games.json" },
    { ["http://server/feed/latest.json"] = "{}",
      ["http://server/feed/latest.epub"] = "re-typeset paper",
      ["http://server/feed/latest.games.json"] = "re-typeset games" }, nil)
assert(read(at(epub)) == "re-typeset paper", "new revision: the paper is fetched again")
assert(read(at("dayfold-2026-11-15-0001.games.json")) == "re-typeset games", "and its puzzles")
assert(store.last_rev == 1700000600, "the new revision is stored")

os.execute("rm -rf '" .. dir .. "'")
print("dayfold plugin sync games: ok")
