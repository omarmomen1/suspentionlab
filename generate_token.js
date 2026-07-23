const { SignJWT } = require('jose');

async function main() {
    const secret = new TextEncoder().encode('');
    const alg = 'HS256';
    
    const jwt = await new SignJWT({ user_id: 'test' })
      .setProtectedHeader({ alg })
      .setExpirationTime('2h')
      .sign(secret);
      
    console.log(jwt);
}

main();
