--[[ Word of the day: on screen keyboard, feedback per letter, progress saved. ]]
local GameBase = require("dayfold_games/base")
local D = require("dayfold_games/draw")

local Wordle = GameBase:extend{ name = "dayfold_wordle" }

local ROWS = { "QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM" }

function Wordle.feedback(guess, answer)
    local res, remaining = {}, {}
    for i = 1, #guess do
        local g, a = guess:sub(i, i), answer:sub(i, i)
        if g == a then res[i] = "correct" else res[i] = "absent"; remaining[a] = (remaining[a] or 0) + 1 end
    end
    for i = 1, #guess do
        local g = guess:sub(i, i)
        if res[i] == "absent" and (remaining[g] or 0) > 0 then
            res[i] = "present"
            remaining[g] = remaining[g] - 1
        end
    end
    return res
end

function Wordle:setup()
    self.answer = self.game.solution.answer
    self.length = self.game.puzzle.length or #self.answer
    self.attempts = self.game.puzzle.attempts or 6
    self.state.guesses = self.state.guesses or {}
    self.current = ""
end

function Wordle:finished()
    local g = self.state.guesses
    return (#g > 0 and g[#g] == self.answer) or #g >= self.attempts
end

function Wordle:letterStates()
    local rank = { absent = 1, present = 2, correct = 3 }
    local states = {}
    for _, guess in ipairs(self.state.guesses) do
        local fb = Wordle.feedback(guess, self.answer)
        for i = 1, #guess do
            local ch = guess:sub(i, i)
            if not states[ch] or rank[fb[i]] > rank[states[ch]] then states[ch] = fb[i] end
        end
    end
    return states
end

local function tile(bb, x, y, s, ch, kind, face)
    if kind == "correct" then
        bb:paintRect(x, y, s, s, D.BLACK)
        D.center(bb, face, ch, x + math.floor(s / 2), y + math.floor(s / 2), true, D.WHITE)
    elseif kind == "present" then
        bb:paintRect(x, y, s, s, D.GRAY)
        D.box(bb, x, y, s, s, 3)
        D.box(bb, x + 6, y + 6, s - 12, s - 12, 1)
        D.center(bb, face, ch, x + math.floor(s / 2), y + math.floor(s / 2), true)
    elseif kind == "absent" then
        D.box(bb, x, y, s, s, 1, D.DARK)
        D.center(bb, face, ch, x + math.floor(s / 2), y + math.floor(s / 2), false, D.DARK)
    else
        D.box(bb, x, y, s, s, 2)
        if ch ~= "" then D.center(bb, face, ch, x + math.floor(s / 2), y + math.floor(s / 2), true) end
    end
end

function Wordle:draw(bb, x, top, w, h)
    local pad = math.floor(w * 0.05)
    local kb_h = math.floor(h * 0.3)
    local board_h = h - kb_h - pad * 2
    local s = math.min(math.floor((w - 2 * pad) / (self.length + 1)), math.floor(board_h / (self.attempts + 0.6)))
    local gap = math.floor(s * 0.12)
    local bw = self.length * s + (self.length - 1) * gap
    local bx = x + math.floor((w - bw) / 2)
    local face = D.face(math.floor(s * 0.55), "tfont")
    for row = 1, self.attempts do
        local y = top + (row - 1) * (s + gap)
        local guess = self.state.guesses[row]
        local fb = guess and Wordle.feedback(guess, self.answer)
        for col = 1, self.length do
            local cx = bx + (col - 1) * (s + gap)
            if guess then
                tile(bb, cx, y, s, guess:sub(col, col), fb[col], face)
            elseif row == #self.state.guesses + 1 and not self:finished() then
                tile(bb, cx, y, s, self.current:sub(col, col), nil, face)
            else
                D.box(bb, cx, y, s, s, 1, D.LIGHT)
            end
        end
    end
    -- keyboard
    local states = self:letterStates()
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
            local enter = { x = rx, y = ry, w = math.floor(kw * 1.5), h = kh, key = "ENTER" }
            table.insert(self.keys, enter)
            D.button(bb, enter, "OK", kf, true)
            rx = rx + enter.w + kgap
        end
        for i = 1, n do
            local ch = letters:sub(i, i)
            local k = { x = rx + (i - 1) * (kw + kgap), y = ry, w = kw, h = kh, key = ch }
            table.insert(self.keys, k)
            local st = states[ch]
            if st == "correct" then
                bb:paintRect(k.x, k.y, k.w, k.h, D.BLACK)
                D.center(bb, kf, ch, k.x + math.floor(k.w / 2), k.y + math.floor(k.h / 2), true, D.WHITE)
            elseif st == "present" then
                bb:paintRect(k.x, k.y, k.w, k.h, D.GRAY)
                D.center(bb, kf, ch, k.x + math.floor(k.w / 2), k.y + math.floor(k.h / 2), true)
            elseif st == "absent" then
                D.box(bb, k.x, k.y, k.w, k.h, 1, D.LIGHT)
                D.center(bb, kf, ch, k.x + math.floor(k.w / 2), k.y + math.floor(k.h / 2), false, D.LIGHT)
            else
                D.button(bb, k, ch, kf)
            end
        end
        if r == 3 then
            local back = { x = rx + n * (kw + kgap), y = ry, w = math.floor(kw * 1.5), h = kh, key = "BACK" }
            table.insert(self.keys, back)
            D.button(bb, back, "<", kf)
        end
    end
    if self:finished() then
        local won = self.state.guesses[#self.state.guesses] == self.answer
        local mf = D.face(math.floor(w * 0.035), "tfont")
        local my = top + self.attempts * (s + gap) + math.floor(gap * 2)
        D.center(bb, mf, won and "Acertou!" or ("Resposta: " .. self.answer), x + math.floor(w / 2), my, true)
    end
end

function Wordle:tap(px, py)
    if self:finished() then return end
    for _, k in ipairs(self.keys or {}) do
        if D.hit(k, px, py) then
            if k.key == "BACK" then
                self.current = self.current:sub(1, -2)
            elseif k.key == "ENTER" then
                if #self.current < self.length then
                    self:flash(string.format("A palavra tem %d letras", self.length))
                    return
                end
                table.insert(self.state.guesses, self.current)
                self.current = ""
                self:save()
                if self:finished() then
                    local won = self.state.guesses[#self.state.guesses] == self.answer
                    self:flash(won and "Parabéns! Palavra descoberta." or ("Fim de jogo: " .. self.answer))
                end
            elseif #self.current < self.length then
                self.current = self.current .. k.key
            end
            self:refresh()
            return
        end
    end
end

return Wordle
