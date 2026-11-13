--[[ Small drawing helpers shared by the game widgets (pure Blitbuffer + RenderText). ]]
local Blitbuffer = require("ffi/blitbuffer")
local Device = require("device")
local Font = require("ui/font")
local RenderText = require("ui/rendertext")
local Screen = Device.screen

local D = {
    BLACK = Blitbuffer.COLOR_BLACK,
    WHITE = Blitbuffer.COLOR_WHITE,
    GRAY = Blitbuffer.COLOR_GRAY,
    LIGHT = Blitbuffer.COLOR_LIGHT_GRAY,
    DARK = Blitbuffer.COLOR_DARK_GRAY,
}

-- Font sizes in real pixels (Font:getFace scales by DPI, so undo that here).
function D.face(px, name)
    local unit = Screen:scaleBySize(1000) / 1000
    return Font:getFace(name or "cfont", math.max(6, math.floor(px / unit)))
end

function D.textWidth(face, text, bold)
    return RenderText:sizeUtf8Text(0, Screen:getWidth() * 2, face, text, true, bold).x
end

-- Draw text centered on (cx, cy).
function D.center(bb, face, text, cx, cy, bold, color)
    local sz = RenderText:sizeUtf8Text(0, Screen:getWidth() * 2, face, text, true, bold)
    local baseline = cy + math.floor((sz.y_top - sz.y_bottom) / 2)
    RenderText:renderUtf8Text(bb, cx - math.floor(sz.x / 2), baseline, face, text, true, bold, color or D.BLACK)
end

-- Draw text with its left edge at x and vertical center at cy.
function D.left(bb, face, text, x, cy, bold, color)
    local sz = RenderText:sizeUtf8Text(0, Screen:getWidth() * 2, face, text, true, bold)
    local baseline = cy + math.floor((sz.y_top - sz.y_bottom) / 2)
    RenderText:renderUtf8Text(bb, x, baseline, face, text, true, bold, color or D.BLACK)
end

function D.box(bb, x, y, w, h, thickness, color)
    bb:paintBorder(x, y, w, h, thickness or 1, color or D.BLACK)
end

-- A newspaper style header: title, double rule and a close button area.
-- Returns the y below the header and the close button rectangle.
function D.header(bb, x, y, w, title, kicker)
    local pad = math.floor(w * 0.04)
    local kf = D.face(math.floor(w * 0.022))
    local tf = D.face(math.floor(w * 0.05), "tfont")
    local top = y + pad
    if kicker then
        D.center(bb, kf, kicker, x + math.floor(w / 2), top + math.floor(w * 0.015))
        top = top + math.floor(w * 0.035)
    end
    D.center(bb, tf, title, x + math.floor(w / 2), top + math.floor(w * 0.035), true)
    local ry = top + math.floor(w * 0.075)
    bb:paintRect(x + pad, ry, w - 2 * pad, 3, D.BLACK)
    bb:paintRect(x + pad, ry + 6, w - 2 * pad, 1, D.BLACK)
    local cs = math.floor(w * 0.075)
    local close = { x = x + w - pad - cs, y = y + pad - math.floor(cs * 0.2), w = cs, h = cs }
    D.center(bb, D.face(math.floor(cs * 0.5)), "×", close.x + math.floor(cs / 2), close.y + math.floor(cs / 2), true)
    return ry + 6 + pad, close
end

function D.hit(r, x, y)
    return r and x >= r.x and x < r.x + r.w and y >= r.y and y < r.y + r.h
end

-- A rectangular button drawn like the dashboard: ink border, small caps feel.
function D.button(bb, r, label, face, inverted)
    if inverted then
        bb:paintRect(r.x, r.y, r.w, r.h, D.BLACK)
        D.center(bb, face, label, r.x + math.floor(r.w / 2), r.y + math.floor(r.h / 2), true, D.WHITE)
    else
        D.box(bb, r.x, r.y, r.w, r.h, 2)
        D.center(bb, face, label, r.x + math.floor(r.w / 2), r.y + math.floor(r.h / 2), true)
    end
end

return D
