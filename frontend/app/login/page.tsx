import type { Metadata } from "next";
import { LoginForm } from "@/components/LoginForm";

export const metadata: Metadata = {
  title: "登录",
};

export default function LoginPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-[#0f172a] px-4">
      <LoginForm />
    </main>
  );
}
