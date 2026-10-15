import type { Metadata } from "next";
import ForgotForm from "@/components/ForgotForm";

export const metadata: Metadata = { title: "Reset your password", robots: { index: false } };

export default function Forgot() {
  return (
    <div className="container section stack">
      <h1>Reset your password</h1>
      <ForgotForm />
    </div>
  );
}
