import type { Metadata } from "next";
import Link from "next/link";
import AuthForm from "@/components/AuthForm";

export const metadata: Metadata = { title: "Log in", robots: { index: false } };

export default function Login() {
  return (
    <div className="container section stack">
      <h1>Log in</h1>
      <AuthForm mode="login" />
      <p>New here? <Link href="/register">Create an account</Link> · <Link href="/forgot-password">Forgot your password?</Link></p>
    </div>
  );
}
