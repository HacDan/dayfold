--[[ Word search: tap the first and the last letter of a word. ]]
local GameBase = require("dayfold_games/base")
local D = require("dayfold_games/draw")
local _ = require("dayfold_l10n")

local WordSearch = GameBase:extend{ name = "dayfold_wordsearch" }

function WordSearch:setup()
    self.rows = self.game.puzzle.rows
    self.size = self.game.puzzle.size or #self.rows
    self.words = self.game.puzzle.words
    self.placements = self.game.solution.placements
    self.state.found = self.state.found or {}
    self.start = nil
end

local function cells(p)
    local r0, c0, r1, c1 = p.start[1], p.start[2], p["end"][1], p["end"][2]
    local n = #p.word
    local dr = (n > 1) and (r1 - r0) / (n - 1) or 0
    local dc = (n > 1) and (c1 - c0) / (n - 1) or 0
    local out = {}
    for k = 0, n - 1 do table.insert(out, { r0 + dr * k, c0 + dc * k }) end
    return out
end

function WordSearch:foundCells()
    local set = {}
    for _, p in ipairs(self.placements) do
        if self.state.found[p.word] then
            for _, rc in ipairs(cells(p)) do set[rc[1] * 100 + rc[2]] = true end
        end
    end
    return set
end

function WordSearch:draw(bb, x, top, w, h)
    local pad = math.floor(w * 0.05)
    local grid = math.min(w - 2 * pad, math.floor(h * 0.68))
    local cell = math.floor(grid / self.size)
    grid = cell * self.size
    local gx = x + math.floor((w - grid) / 2)
    local gy = top
    self.grid_rect = { x = gx, y = gy, w = grid, h = grid, cell = cell }
    local face = D.face(math.floor(cell * 0.55), "tfont")
    local hits = self:foundCells()
    D.box(bb, gx - 2, gy - 2, grid + 4, grid + 4, 2)
    for r = 0, self.size - 1 do
        local row = self.rows[r + 1]
        for c = 0, self.size - 1 do
            local cx, cy = gx + c * cell, gy + r * cell
            local ch = row:sub(c + 1, c + 1)
            if hits[r * 100 + c] then
                bb:paintRect(cx + 1, cy + 1, cell - 2, cell - 2, D.BLACK)
                D.center(bb, face, ch, cx + math.floor(cell / 2), cy + math.floor(cell / 2), true, D.WHITE)
            elseif self.start and self.start[1] == r and self.start[2] == c then
                bb:paintRect(cx + 1, cy + 1, cell - 2, cell - 2, D.GRAY)
                D.center(bb, face, ch, cx + math.floor(cell / 2), cy + math.floor(cell / 2), true)
            else
                D.center(bb, face, ch, cx + math.floor(cell / 2), cy + math.floor(cell / 2), false)
            end
        end
    end
    -- word list in columns
    local ly = gy + grid + math.floor(pad * 0.8)
    local cols = 3
    local colw = math.floor((w - 2 * pad) / cols)
    local lf = D.face(math.floor(w * 0.03))
    local lh = math.floor(w * 0.045)
    local count = 0
    for i, word in ipairs(self.words) do
        local col = (i - 1) % cols
        local line = math.floor((i - 1) / cols)
        local wx = x + pad + col * colw
        local wy = ly + line * lh + math.floor(lh / 2)
        local found = self.state.found[word]
        D.left(bb, lf, word, wx, wy, not found, found and D.GRAY or D.BLACK)
        if found then
            count = count + 1
            local tw = D.textWidth(lf, word, false)
            bb:paintRect(wx, wy, tw, 2, D.BLACK)
        end
    end
    local sf = D.face(math.floor(w * 0.026))
    local sy = ly + math.ceil(#self.words / cols) * lh + math.floor(lh * 0.6)
    D.center(bb, sf, string.format(_("%d of %d words · theme: %s"), count, #self.words, self.game.puzzle.theme or ""), x + math.floor(w / 2), sy)
end

function WordSearch:tap(px, py)
    local g = self.grid_rect
    if not (g and D.hit(g, px, py)) then return end
    local c = math.floor((px - g.x) / g.cell)
    local r = math.floor((py - g.y) / g.cell)
    if not self.start then
        self.start = { r, c }
        self:refresh()
        return
    end
    local a, b = self.start, { r, c }
    self.start = nil
    for _, p in ipairs(self.placements) do
        local s, e = p.start, p["end"]
        if (s[1] == a[1] and s[2] == a[2] and e[1] == b[1] and e[2] == b[2])
            or (s[1] == b[1] and s[2] == b[2] and e[1] == a[1] and e[2] == a[2]) then
            if not self.state.found[p.word] then
                self.state.found[p.word] = true
                self:save()
                local n = 0
                for _ in pairs(self.state.found) do n = n + 1 end
                if n == #self.words then self:flash(_("Well done! All words found."))
                else self:flash(p.word .. "!") end
            end
            return self:refresh()
        end
    end
    self:refresh()
end

return WordSearch
