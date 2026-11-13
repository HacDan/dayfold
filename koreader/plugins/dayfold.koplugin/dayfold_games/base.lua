--[[ Full screen game widget base: white page, tap dispatch, close handling. ]]
local Device = require("device")
local Geom = require("ui/geometry")
local GestureRange = require("ui/gesturerange")
local InputContainer = require("ui/widget/container/inputcontainer")
local UIManager = require("ui/uimanager")
local D = require("dayfold_games/draw")
local Screen = Device.screen

local GameBase = InputContainer:extend{
    name = "dayfold_game",
    covers_fullscreen = true,
    game = nil,          -- entry from games.json
    state = nil,         -- persisted state table
    on_save = nil,       -- function(state)
    on_close = nil,      -- function()
    edition_title = "Dayfold",
}

function GameBase:init()
    self.dimen = Geom:new{ x = 0, y = 0, w = Screen:getWidth(), h = Screen:getHeight() }
    self.ges_events = {
        Tap = { GestureRange:new{ ges = "tap", range = self.dimen } },
    }
    if Device:hasKeys() then
        self.key_events = { Close = { { Device.input.group.Back } } }
    end
    self.state = self.state or {}
    self.message = nil
    if self.setup then self:setup() end
end

function GameBase:paintTo(bb, x, y)
    self.dimen.x, self.dimen.y = x, y
    bb:paintRect(x, y, self.dimen.w, self.dimen.h, D.WHITE)
    local top
    top, self.close_rect = D.header(bb, x, y, self.dimen.w, self.game.title, self.edition_title)
    self:draw(bb, x, top, self.dimen.w, self.dimen.h - (top - y))
    if self.message then
        local mf = D.face(math.floor(self.dimen.w * 0.032))
        local mh = math.floor(self.dimen.h * 0.06)
        local my = y + self.dimen.h - mh - math.floor(self.dimen.h * 0.01)
        bb:paintRect(x, my, self.dimen.w, mh, D.BLACK)
        D.center(bb, mf, self.message, x + math.floor(self.dimen.w / 2), my + math.floor(mh / 2), true, D.WHITE)
    end
end

function GameBase:refresh(full)
    UIManager:setDirty(self, function()
        return full and "full" or "ui", self.dimen
    end)
end

function GameBase:flash(msg)
    self.message = msg
    self:refresh()
    UIManager:scheduleIn(2.5, function()
        if self.message == msg then
            self.message = nil
            self:refresh()
        end
    end)
end

function GameBase:save()
    if self.on_save then self.on_save(self.state) end
end

function GameBase:onTap(_, ges)
    local px, py = ges.pos.x, ges.pos.y
    if D.hit(self.close_rect, px, py) then
        return self:onClose()
    end
    if self.tap then self:tap(px, py) end
    return true
end

function GameBase:onClose()
    self:save()
    UIManager:close(self, "full")
    if self.on_close then self.on_close() end
    return true
end

function GameBase:onShow()
    self:refresh(true)
end

return GameBase
