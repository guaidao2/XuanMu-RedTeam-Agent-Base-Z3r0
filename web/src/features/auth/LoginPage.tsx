import { Button, Input } from "@douyinfe/semi-ui";
import { Crosshair, KeyRound, Mail } from "lucide-react";
import { FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { login } from "../../shared/api/systemUsers";
import { showApiError } from "../../shared/api/feedback";
import { useAuth } from "../../shared/auth/AuthProvider";
import xuanmuLogo from "../../assets/xuanmu-logo.svg";

type LoginLocationState = {
  from?: { pathname?: string };
};

export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as LoginLocationState | null)?.from?.pathname || "/playground";

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    try {
      const response = await login({ email, password });
      if (response.data?.token) {
        signIn(response.data.token);
        navigate(from, { replace: true });
      }
    } catch (error) {
      showApiError(error);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="login-page">
      <div className="login-grid" aria-hidden="true" />
      <div className="login-scanline" aria-hidden="true" />
      <section className="login-panel" aria-labelledby="login-title">
        <div className="login-brand">
          <img className="brand-logo large" src={xuanmuLogo} alt="" />
          <div>
            <span className="login-kicker">红队智能体协作平台</span>
            <h1 id="login-title">XuanMu Console</h1>
          </div>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          <label>
            <span>Email</span>
            <Input
              size="large"
              type="email"
              prefix={<Mail size={16} />}
              value={email}
              onChange={setEmail}
              autoComplete="email"
              placeholder="<your email>"
              required
            />
          </label>
          <label>
            <span>Password</span>
            <Input
              size="large"
              mode="password"
              prefix={<KeyRound size={16} />}
              value={password}
              onChange={setPassword}
              autoComplete="current-password"
              placeholder="<your password>"
              required
            />
          </label>
          <Button
            htmlType="submit"
            theme="solid"
            type="primary"
            size="large"
            block
            loading={submitting}
            icon={<Crosshair size={17} />}
          >
            Sign in
          </Button>
        </form>
        <div className="login-credit">
          Based on <a href="https://github.com/yv1ing/Z3r0" target="_blank" rel="noopener noreferrer">Z3r0</a>
        </div>
      </section>
    </main>
  );
}
