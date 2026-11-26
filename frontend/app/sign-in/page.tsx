import { redirect } from "next/navigation";

/**
 * /sign-in is a legacy/external alias for the canonical login route.
 * Redirect (server-side, 307) so old links never 404.
 */
export default function SignInRedirect() {
  redirect("/auth/login");
}
