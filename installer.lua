-- ==========================================
-- MULTI-SELECT SMART UPDATE SCRIPT (TERMUX/ROOT FIX)
-- ==========================================

local WEB_URL = "https://api.amer.web.id/ronpig" 

-- Helper: Execute a command and get the output
local function get_command_output(cmd)
    local handle = io.popen(cmd)
    local result = handle:read("*a")
    if handle then handle:close() end
    return result
end

-- Get current directory to ensure absolute paths for the initial download
local PWD = get_command_output("pwd"):gsub("%s+", "")
local TEMP_APK = PWD .. "/temp_install.apk"
local SAFE_TEMP = "/data/local/tmp/temp_install.apk"

-- Helper: Split a string by a delimiter
local function split(s, delimiter)
    local result = {}
    for match in (s..delimiter):gmatch("(.-)"..delimiter) do
        table.insert(result, match)
    end
    return result
end

function main()
    print("🌐 Scanning Web Directory: " .. WEB_URL)

    local html = get_command_output("curl -sL " .. WEB_URL)
    
    if not html or html == "" then
        print("❌ Failed to reach the web server. Is it running?")
        return
    end

    local apk_files = {}
    for match in string.gmatch(html, 'href="([^"]+%.apk)"') do
        table.insert(apk_files, match)
    end

    if #apk_files == 0 then
        print("⚠️ No APK files found on the server.")
        return
    end

    print("\n📦 Available Files:")
    print("----------------------------------------")
    for i, apk in ipairs(apk_files) do
        local display_name = apk:gsub("%%20", " ") 
        print(string.format("[%d] %s", i, display_name))
    end
    print("----------------------------------------")

    print("\n🔢 Which files do you want to install?")
    io.write("   (e.g., '1', '1,3,4', or '1-3'): ")
    local choice = io.read()

    if not choice or choice == "" then
        print("❌ No selection made. Exiting.")
        return
    end

    local selected_indices = {}
    for _, part in ipairs(split(choice, ",")) do
        part = part:gsub("%s+", "")
        if part:find("-") then
            local s, e = part:match("(%d+)%-(%d+)")
            if s and e then
                for i = tonumber(s), tonumber(e) do
                    selected_indices[i] = true
                end
            end
        elseif tonumber(part) then
            selected_indices[tonumber(part)] = true
        end
    end

    print("\n🚀 Starting Process...")
    for i, apk_name in ipairs(apk_files) do
        if selected_indices[i] then
            local display_name = apk_name:gsub("%%20", " ")
            print("\n----------------------------------------")
            print("⬇️ Downloading: " .. display_name)
            
            local download_url = WEB_URL .. apk_name
            
            -- 1. Download to local Termux folder where curl has permissions
            local curl_cmd = 'curl -f -# -L -o "' .. TEMP_APK .. '" "' .. download_url .. '"'
            local dl_success = os.execute(curl_cmd)

            if dl_success == true or dl_success == 0 then
                print("   ✅ Download complete. Moving to staging area...")
                
                -- 2. Move file to the safe directory using root
                os.execute(string.format("su -c 'mv \"%s\" \"%s\"'", TEMP_APK, SAFE_TEMP))
                
                -- 3. Grant read permissions so System Server can see it
                os.execute(string.format("su -c 'chmod 644 \"%s\"'", SAFE_TEMP))
                
                print("   ⚙️ Installing...")
                -- 4. Install from the safe directory
                local install_cmd = string.format("su -c 'pm install -r -d \"%s\"'", SAFE_TEMP)
                local inst_success = os.execute(install_cmd)
                
                if inst_success == true or inst_success == 0 then
                    print("   🎉 Successfully installed!")
                else
                    print("   ❌ Failed to install via package manager.")
                end
                
                -- 5. Clean up the safe temp file
                os.execute(string.format("su -c 'rm \"%s\"'", SAFE_TEMP))
            else
                print("   ❌ Download failed. Skipping.")
                -- Clean up local temp file just in case it partially downloaded
                os.execute('rm -f "' .. TEMP_APK .. '"')
            end
        end
    end
    
    print("\n✅ All tasks completed!")
end


main()
