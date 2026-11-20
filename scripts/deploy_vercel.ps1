$vercelJs = "D:\npm-cache\_npx\69f9afb961c37556\node_modules\vercel\dist\vc.js"
$dnsFix = "D:/project/scripts/dns_fix.js"

Set-Location d:\project\backend_vercel
Write-Host "Deploying backend_vercel..."
node -r $dnsFix $vercelJs --prod --yes
$backendExit = $LASTEXITCODE

Set-Location d:\project\frontend
Write-Host "Deploying frontend..."
node -r $dnsFix $vercelJs --prod --yes
$frontendExit = $LASTEXITCODE

Write-Host "Backend exit: $backendExit, Frontend exit: $frontendExit"
