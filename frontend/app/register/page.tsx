import type { Metadata } from "next";
import Link from "next/link";
import AuthForm from "@/components/AuthForm";

export const metadata: Metadata = { title: "Create an account", robots: { index: false } };

export default function Register() {
  return (
    <div className="container section stack">
      <h1>Create your account</h1>
      <AuthForm mode="register" />
      <p>Already registered? <Link href="/login">Log in</Link></p>
    </div>
  );
}
