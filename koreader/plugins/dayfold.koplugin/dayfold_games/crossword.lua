--[[ Crossword: tap a square (tap it again to switch across/down), type on the keyboard. ]]
local GameBase = require("dayfold_games/base")
local D = require("dayfold_games/draw")

local Crossword = GameBase:extend{ name = "dayfold_crossword" }

local ROWS = { "QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM" }
local DIRS = { across = { 0, 1 }, down = { 1, 0 } }

local function key(r, c) return r .. "," .. c end

function Crossword:setup()
    local p = self.game.puzzle
    self.grid = p.grid
    self.rows, self.cols = p.rows or #p.grid, p.cols or #p.grid[1]
    self.answer = self.game.solution.grid
    self.numbers = {}
    for _, t in ipairs(p.numbers or {}) do self.numbers[key(t[1], t[2])] = t[3] end
    -- every open square knows the entry it belongs to in each direction
    self.entries, self.at = {}, {}
    for dir, d in pairs(DIRS) do
        for _, e in ipairs(p[dir] or {}) do
            local entry = { n = e.n, row = e.row, col = e.col, len = e.len, clue = e.clue, dir = dir }
            table.insert(self.entries, entry)
            for k = 0, e.len - 1 do
                local id = key(e.row + d[1] * k, e.col + d[2] * k)
                self.at[id] = self.at[id] or {}
                self.at[id][dir] = entry
            end
        end
    end
    if type(self.state.cells) ~= "table" then self.state.cells = {} end
    local first = (p.across and p.across[1]) or (p.down and p.down[1])
    self.dir = (p.across and p.across[1]) and "across" or "down"
    self.sel = first and { first.row, first.col } or nil
end

function Crossword:open(r, c)
    return r >= 0 and c >= 0 and r < self.rows and c < self.cols and self.grid[r + 1]:sub(c + 1, c + 1) ~= "#"
end

function Crossword:entry()
    if not self.sel then return nil end
    local here = self.at[key(self.sel[1], self.sel[2])] or {}
    return here[self.dir] or here.across or here.down
end

local function wrap(face, text, maxw)
    local lines, line = {}, ""
    for word in text:gmatch("%S+") do
        local try = line == "" and word or (line .. " " .. word)
        if line ~= "" and D.textWidth(face, try, false) > maxw then
            table.insert(lines, line)
            line = word
        else
            line = try
        end
    end
    if line ~= "" then table.insert(lines, line) end
    return lines
end

function Crossword:draw(bb, x, top, w, h)
    local pad = math.floor(w * 0.05)
    local kb_h = math.floor(h * 0.27)
    local clue_h = math.floor(h * 0.1)
    local avail_h = h - kb_h - clue_h - pad * 2
    local cell = math.floor(math.min((w - 2 * pad) / self.cols, avail_h / self.rows))
    local gx = x + math.floor((w - cell * self.cols) / 2)
    local gy = top
    self.grid_rect = { x = gx, y = gy, w = cell * self.cols, h = cell * self.rows, cell = cell }
    local entry = self:entry()
    local in_entry = {}
    if entry then
        local d = DIRS[entry.dir]
        for k = 0, entry.len - 1 do in_entry[key(entry.row + d[1] * k, entry.col + d[2] * k)] = true end
    end
    local lf = D.face(math.floor(cell * 0.55), "tfont")
    local nf = D.face(math.max(8, math.floor(cell * 0.24)))
    for r = 0, self.rows - 1 do
        for c = 0, self.cols - 1 do
            if self:open(r, c) then
                local id = key(r, c)
                local cx, cy = gx + c * cell, gy + r * cell
                local selected = self.sel and self.sel[1] == r and self.sel[2] == c
                if selected then
                    bb:paintRect(cx, cy, cell, cell, D.GRAY)
                elseif in_entry[id] then
                    bb:paintRect(cx, cy, cell, cell, D.LIGHT)
                end
                D.box(bb, cx, cy, cell + 1, cell + 1, 2)
                if self.numbers[id] then
                    D.left(bb, nf, tostring(self.numbers[id]), cx + 3, cy + math.floor(cell * 0.16), false)
                end
                local ch = self.state.cells[id]
                if ch and ch ~= "" then
                    D.center(bb, lf, ch, cx + math.floor(cell / 2), cy + math.floor(cell * 0.58), true)
                end
            end
        end
    end
    -- current clue
    if entry then
        local cf = D.face(math.floor(w * 0.03))
        local label = string.format("%d %s: %s (%d)", entry.n, entry.dir == "across" and "Horizontal" or "Vertical",
            entry.clue, entry.len)
        local lines = wrap(cf, label, w - 2 * pad)
        local lh = math.floor(w * 0.042)
        local cy = gy + self.grid_rect.h + math.floor(pad * 0.6)
        for i = 1, math.min(#lines, 2) do
            D.center(bb, cf, lines[i], x + math.floor(w / 2), cy + math.floor((i - 0.5) * lh), i == 1)
        end
    end
    -- keyboard
    local ky = top + h - kb_h - pad
    local kh = math.floor(kb_h / 3.3)
    local kw = math.floor((w - 2 * pad) / 10.6)
    local kgap = math.floor(kw * 0.06)
    local kf = D.face(math.floor(kh * 0.42), "tfont")
    self.keys = {}
    for r, letters in ipairs(ROWS) do
        local n = #letters
        local extra = (r == 3) and 2 or 0
        local rowW = n * kw + (n - 1) * kgap + extra * (math.floor(kw * 1.5) + kgap)
        local rx = x + math.floor((w - rowW) / 2)
        local ry = ky + (r - 1) * (kh + kgap)
        if r == 3 then
            local turn = { x = rx, y = ry, w = math.floor(kw * 1.5), h = kh, key = "TURN" }
            table.insert(self.keys, turn)
            D.button(bb, turn, self.dir == "across" and "H" or "V", kf, true)
            rx = rx + turn.w + kgap
        end
        for i = 1, n do
            local k = { x = rx + (i - 1) * (kw + kgap), y = ry, w = kw, h = kh, key = letters:sub(i, i) }
            table.insert(self.keys, k)
            D.button(bb, k, k.key, kf)
        end
        if r == 3 then
            local back = { x = rx + n * (kw + kgap), y = ry, w = math.floor(kw * 1.5), h = kh, key = "BACK" }
            table.insert(self.keys, back)
            D.button(bb, back, "<", kf)
        end
    end
end

function Crossword:step(delta)
    local entry = self:entry()
    if not entry then return end
    local d = DIRS[entry.dir]
    local r, c = self.sel[1] + d[1] * delta, self.sel[2] + d[2] * delta
    local last_r, last_c = entry.row + d[1] * (entry.len - 1), entry.col + d[2] * (entry.len - 1)
    if r >= entry.row and c >= entry.col and r <= last_r and c <= last_c then
        self.sel = { r, c }
        self.dir = entry.dir
    end
end

function Crossword:checkComplete()
    local wrong = 0
    for r = 0, self.rows - 1 do
        for c = 0, self.cols - 1 do
            if self:open(r, c) then
                local ch = self.state.cells[key(r, c)]
                if not ch or ch == "" then return end
                if ch ~= self.answer[r + 1]:sub(c + 1, c + 1) then wrong = wrong + 1 end
            end
        end
    end
    if wrong == 0 then
        if not self.state.done then
            self.state.done = true
            self:save()
        end
        self:flash("Parabéns! Cruzadas completas.")
    else
        self:flash(string.format("Grade cheia, mas %d letra(s) errada(s).", wrong))
    end
end

function Crossword:tap(px, py)
    local g = self.grid_rect
    if g and D.hit(g, px, py) then
        local c = math.floor((px - g.x) / g.cell)
        local r = math.floor((py - g.y) / g.cell)
        if not self:open(r, c) then return end
        local here = self.at[key(r, c)] or {}
        if self.sel and self.sel[1] == r and self.sel[2] == c then
            local other = self.dir == "across" and "down" or "across"
            if here[other] then self.dir = other end
        else
            self.sel = { r, c }
            if not here[self.dir] then self.dir = here.across and "across" or "down" end
        end
        return self:refresh()
    end
    for _, k in ipairs(self.keys or {}) do
        if D.hit(k, px, py) then
            if not self.sel then return end
            local id = key(self.sel[1], self.sel[2])
            if k.key == "TURN" then
                local here = self.at[id] or {}
                local other = self.dir == "across" and "down" or "across"
                if here[other] then self.dir = other end
            elseif k.key == "BACK" then
                if self.state.cells[id] and self.state.cells[id] ~= "" then
                    self.state.cells[id] = nil
                else
                    self:step(-1)
                    self.state.cells[key(self.sel[1], self.sel[2])] = nil
                end
                self:save()
            else
                self.state.cells[id] = k.key
                self:step(1)
                self:save()
                self:checkComplete()
            end
            return self:refresh()
        end
    end
end

return Crossword
