--[[ Interactive Sudoku: tap a cell, then a number. Givens are fixed. ]]
local GameBase = require("dayfold_games/base")
local D = require("dayfold_games/draw")
local _ = require("dayfold_l10n")

local Sudoku = GameBase:extend{ name = "dayfold_sudoku" }

function Sudoku:setup()
    self.puzzle = self.game.puzzle.grid
    self.solution = self.game.solution.grid
    if type(self.state.values) ~= "table" or #self.state.values ~= 81 then
        self.state.values = {}
        for i = 1, 81 do self.state.values[i] = 0 end
    end
    self.selected = nil
    self.errors = {}
end

function Sudoku:value(i)
    local given = self.puzzle[i]
    if given and given > 0 then return given, true end
    return self.state.values[i] or 0, false
end

function Sudoku:draw(bb, x, top, w, h)
    local pad = math.floor(w * 0.05)
    local grid = math.min(w - 2 * pad, math.floor(h * 0.6))
    local cell = math.floor(grid / 9)
    grid = cell * 9
    local gx = x + math.floor((w - grid) / 2)
    local gy = top
    self.grid_rect = { x = gx, y = gy, w = grid, h = grid, cell = cell }
    local fgiven = D.face(math.floor(cell * 0.58), "tfont")
    local fuser = D.face(math.floor(cell * 0.55))
    for r = 0, 8 do
        for c = 0, 8 do
            local i = r * 9 + c + 1
            local cx, cy = gx + c * cell, gy + r * cell
            if self.selected == i then
                bb:paintRect(cx, cy, cell, cell, D.LIGHT)
            elseif self.errors[i] then
                bb:paintRect(cx, cy, cell, cell, D.GRAY)
            end
            local v, given = self:value(i)
            if v > 0 then
                D.center(bb, given and fgiven or fuser, tostring(v), cx + math.floor(cell / 2), cy + math.floor(cell / 2), given, given and D.BLACK or D.DARK)
            end
        end
    end
    for k = 0, 9 do
        local t = (k % 3 == 0) and 4 or 1
        bb:paintRect(gx + k * cell - math.floor(t / 2), gy, t, grid, D.BLACK)
        bb:paintRect(gx, gy + k * cell - math.floor(t / 2), grid, t, D.BLACK)
    end
    -- keypad
    local ky = gy + grid + math.floor(pad * 0.8)
    local kw = math.floor((w - 2 * pad - 4 * math.floor(pad / 3)) / 5)
    local kh = math.floor(math.min(kw * 0.8, (h - grid - pad * 3) / 3.3))
    local gap = math.floor(pad / 3)
    local kf = D.face(math.floor(kh * 0.5), "tfont")
    self.keys = {}
    local labels = { "1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫" }
    for n = 1, 10 do
        local row = (n <= 5) and 0 or 1
        local col = (n - 1) % 5
        local r = { x = x + pad + col * (kw + gap), y = ky + row * (kh + gap), w = kw, h = kh, value = (n == 10) and 0 or n }
        table.insert(self.keys, r)
        D.button(bb, r, n == 10 and "×" or labels[n], kf)
    end
    local ay = ky + 2 * (kh + gap) + gap
    local aw = math.floor((w - 2 * pad - gap) / 2)
    local af = D.face(math.floor(kh * 0.32), "tfont")
    self.check_rect = { x = x + pad, y = ay, w = aw, h = math.floor(kh * 0.8) }
    self.clear_rect = { x = x + pad + aw + gap, y = ay, w = aw, h = math.floor(kh * 0.8) }
    D.button(bb, self.check_rect, _("CHECK"), af, true)
    D.button(bb, self.clear_rect, _("RESTART"), af)
end

function Sudoku:tap(px, py)
    local g = self.grid_rect
    if g and D.hit(g, px, py) then
        local c = math.floor((px - g.x) / g.cell)
        local r = math.floor((py - g.y) / g.cell)
        local i = r * 9 + c + 1
        if self.puzzle[i] == 0 then
            self.selected = (self.selected == i) and nil or i
            self:refresh()
        end
        return
    end
    for _, k in ipairs(self.keys or {}) do
        if D.hit(k, px, py) then
            if self.selected then
                self.state.values[self.selected] = k.value
                self.errors[self.selected] = nil
                self:save()
                self:checkComplete()
                self:refresh()
            else
                self:flash(_("Tap an empty cell first"))
            end
            return
        end
    end
    if D.hit(self.check_rect, px, py) then
        local wrong, empty = 0, 0
        self.errors = {}
        for i = 1, 81 do
            local v = self:value(i)
            if v == 0 then empty = empty + 1
            elseif v ~= self.solution[i] then wrong = wrong + 1; self.errors[i] = true end
        end
        if wrong == 0 and empty == 0 then self:flash(_("Perfect! Sudoku solved."))
        elseif wrong == 0 then self:flash(string.format(_("All good so far. %d cells to go."), empty))
        else self:flash(string.format(_("%d wrong cell(s) marked in gray."), wrong)) end
        self:refresh()
    elseif D.hit(self.clear_rect, px, py) then
        for i = 1, 81 do self.state.values[i] = 0 end
        self.errors, self.selected, self.state.done = {}, nil, false
        self:save()
        self:refresh(true)
    end
end

function Sudoku:checkComplete()
    for i = 1, 81 do
        if self:value(i) ~= self.solution[i] then return end
    end
    if not self.state.done then
        self.state.done = true
        self:save()
        self:flash(_("Well done! Sudoku solved."))
    end
end

return Sudoku
