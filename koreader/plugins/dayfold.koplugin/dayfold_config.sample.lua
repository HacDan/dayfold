-- Copy to dayfold_config.lua (same folder) and fill in your server.
-- The dashboard (Kindle page) shows the exact values for your install.
return {
    server = "http://192.168.0.10:8422", -- Dayfold server, no trailing slash
    token = "PASTE-THE-FEED-TOKEN",      -- Settings > Kindle in the dashboard
    keep = 7,                            -- editions kept on the device
    folder = nil,                        -- default: <home folder>/Dayfold
}
