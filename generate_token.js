const { SignJWT } = require('jose');

async function main() {
    const rawSecret = process.env.JWT_SECRET || process.env.JWT_SECRET_KEY;
    if (!rawSecret || rawSecret.length < 32) {
        console.error("CRITICAL: JWT_SECRET or JWT_SECRET_KEY environment variable is required and must be >= 32 characters.");
        process.exit(1);
    }
    const secret = new TextEncoder().encode(rawSecret);
    const alg = 'HS256';
    
    const jwt = await new SignJWT({ user_id: 'test' })
      .setProtectedHeader({ alg, kid: 'v1' })
      .setExpirationTime('2h')
      .sign(secret);
      
    console.log(jwt);
}

main();
