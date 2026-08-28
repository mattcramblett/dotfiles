local M = {}

-- Check for an existing non-expired SSO session and update BEDROCK_KEYS.
function M.try_to_set_bedrock_keys()
	-- Locate the AWS CLI cache directory.
	local cache_path = vim.fn.expand("~/.aws/cli/cache/")
	local files = vim.fn.globpath(cache_path, "*.json", false, true)

	if #files == 0 then
		print("No AWS session detected for Bedrock. Run :Bedrock to authenticate.")
		return
	end

	local valid_cred = nil
	local current_time = os.time()

	-- Loop through each JSON file to look for a valid session.
	local selected_file = nil

	for _, file in ipairs(files) do
		local f = io.open(file, "r")
		if f then
			selected_file = f

			local content = f:read("*a")
			f:close()

			local ok, cred_data = pcall(vim.fn.json_decode, content)
			if ok and cred_data then
				-- Credentials may be nested under "roleCredentials" or at the top level.
				local credentials = cred_data.Credentials or cred_data

				-- Check for an expiration key (it might be "expiration" or "Expiration").
				local expiration = credentials.Expiration or cred_data.expiration
				if expiration then
					-- Attempt to parse an ISO 8601 date (example: "2023-10-12T15:30:00Z").
					local y, m, d, h, min, s = expiration:match("^(%d+)%-(%d+)%-(%d+)T(%d+):(%d+):(%d+)Z")
					if y then
						local exp_time = os.time({
							year = tonumber(y) or 2025,
							month = tonumber(m) or 1,
							day = tonumber(d) or 1,
							hour = tonumber(h),
							min = tonumber(min),
							sec = tonumber(s),
						})
						if current_time < exp_time then
							valid_cred = credentials
              selected_file = file
							break
						end
					end
				else
					-- If no expiration key exists, assume the credentials are valid.
					valid_cred = credentials
          selected_file = file
					break
				end
			end
		end
	end

	if not valid_cred then
    print("No AWS credentials in the selected file: " .. (selected_file or "unknown"))
		return
	end

	-- Extract the necessary credential values.
	local access_key = valid_cred.AccessKeyId or valid_cred.accessKeyId
	local secret_key = valid_cred.SecretAccessKey or valid_cred.secretAccessKey
	local session_token = valid_cred.SessionToken or valid_cred.sessionToken

	if not (access_key and secret_key and session_token) then
		print("Incomplete AWS credentials in the selected file." .. (selected_file or "unknown"))
		return
	end

	-- Retrieve the AWS region for the 'playground' profile.
	local region_cmd = "aws configure get region --profile playground"
	local region = vim.fn.system(region_cmd)
	region = vim.trim(region)
	if region == "" then
		print("Failed to retrieve AWS region for profile 'playground'.")
		return
	end

	-- Format the BEDROCK_KEYS variable as a comma-separated string.
	local bedrock_keys_value = string.format("%s,%s,%s,%s", access_key, secret_key, region, session_token)
	vim.env.BEDROCK_KEYS = bedrock_keys_value

	print("AWS Bedrock Session found")
end

-- Login via SSO and update keys
function M.update_bedrock_keys()
	-- 1. Trigger AWS SSO login for the 'playground' profile.
	local login_cmd = "aws sso login --profile playground"
	local login_output = vim.fn.system(login_cmd)
	if vim.v.shell_error ~= 0 then
		print("AWS SSO login failed. Please check your AWS configuration.")
		return
	end

	-- 2. Get a list of credential JSON files from the cache directory.
	local cache_path = vim.fn.expand("~/.aws/cli/cache/")
	local files = vim.fn.globpath(cache_path, "*.json", false, true)
	if #files == 0 then
		print("No AWS credential files found in the cache.")
		return
	end

	-- 3. Loop through the files to select a valid (non-expired) credential.
	local valid_cred = nil
	local current_time = os.time()
	for _, file in ipairs(files) do
		local f = io.open(file, "r")
		if f then
			local content = f:read("*a")
			f:close()
			local ok, cred_data = pcall(vim.fn.json_decode, content)
			if ok and cred_data then
				-- Credentials may be stored under "roleCredentials" or at the top level.
				local credentials = cred_data.Credentials or cred_data
				local expiration = credentials.expiration or cred_data.Expiration
				if expiration then
					if type(expiration) == "number" then
						-- Assume the numeric expiration is in milliseconds.
						local exp_seconds = expiration / 1000
						if current_time < exp_seconds then
							valid_cred = credentials
							break
						end
					elseif type(expiration) == "string" then
						-- Attempt to parse an ISO 8601 formatted date e.g., "2023-10-12T15:30:00Z"
						local y, m, d, h, min, s = expiration:match("^(%d+)%-(%d+)%-(%d+)T(%d+):(%d+):(%d+)Z")
						if y then
							local exp_time = os.time({
								year = tonumber(y) or 2025,
								month = tonumber(m) or 1,
								day = tonumber(d) or 1,
								hour = tonumber(h),
								min = tonumber(min),
								sec = tonumber(s),
							})
							if current_time < exp_time then
								valid_cred = credentials
								break
							end
						end
					end
				else
					-- If there's no expiration key, assume the credentials are valid.
					valid_cred = credentials
					break
				end
			end
		end
	end

	if not valid_cred then
		print("No valid (non-expired) AWS credentials found.")
		return
	end

	-- 4. Extract the necessary credential values.
	local access_key = valid_cred.AccessKeyId or valid_cred.accessKeyId
	local secret_key = valid_cred.SecretAccessKey or valid_cred.secretAccessKey
	local session_token = valid_cred.SessionToken or valid_cred.sessionToken

	if not (access_key and secret_key and session_token) then
		print("Incomplete AWS credentials in the selected file.")
		return
	end

	-- 5. Retrieve the AWS region for the profile.
	local region_cmd = "aws configure get region --profile playground"
	local region = vim.fn.system(region_cmd)
	region = vim.trim(region)
	if region == "" then
		print("Failed to retrieve AWS region for profile 'playground'.")
		return
	end

	-- 6. Format the BEDROCK_KEYS string.
	local bedrock_keys_value = string.format("%s,%s,%s,%s", access_key, secret_key, region, session_token)
	vim.env.BEDROCK_KEYS = bedrock_keys_value

	print("AWS Bedrock is ready!")
end

return M
