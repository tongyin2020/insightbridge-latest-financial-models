import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Bot, Lock, Mail, User, AlertCircle, ArrowRight, ShieldCheck, ArrowLeft } from 'lucide-react';

const AuthPage = () => {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  
  // 2FA state
  const [needs2FA, setNeeds2FA] = useState(false);
  const [otpCode, setOtpCode] = useState('');
  const [pending2FAUserId, setPending2FAUserId] = useState('');
  
  const { login, register, verify2FA } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      let result;
      if (isLogin) {
        result = await login(email, password);
      } else {
        if (!name.trim()) {
          setError('Name is required');
          setLoading(false);
          return;
        }
        result = await register(email, password, name);
      }

      if (result.success) {
        navigate('/dashboard');
      } else if (result.requires_2fa) {
        setNeeds2FA(true);
        setPending2FAUserId(result.user_id);
        setError('');
      } else {
        setError(result.error);
      }
    } catch (err) {
      setError('An unexpected error occurred');
    } finally {
      setLoading(false);
    }
  };

  const handle2FASubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const result = await verify2FA(pending2FAUserId, otpCode);
      if (result.success) {
        navigate('/dashboard');
      } else {
        setError(result.error || 'Invalid 2FA code');
      }
    } catch (err) {
      setError('Failed to verify 2FA code');
    } finally {
      setLoading(false);
    }
  };

  const resetTo2FALogin = () => {
    setNeeds2FA(false);
    setOtpCode('');
    setPending2FAUserId('');
    setError('');
  };

  return (
    <div 
      className="min-h-screen flex items-center justify-center bg-zinc-950 p-4"
      style={{
        backgroundImage: `url('https://images.unsplash.com/photo-1761078739436-ccee01f3d89c?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjY2NzN8MHwxfHNlYXJjaHwxfHxhYnN0cmFjdCUyMGRhcmslMjB0ZXh0dXJlJTIwYmFja2dyb3VuZHxlbnwwfHx8fDE3NzUxMzc2NDF8MA&ixlib=rb-4.1.0&q=85')`,
        backgroundSize: 'cover',
        backgroundPosition: 'center'
      }}
    >
      <div className="absolute inset-0 bg-zinc-950/80 backdrop-blur-sm" />
      
      <div className="relative z-10 w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-600 rounded-sm mb-4">
            <Bot className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-black tracking-tight text-zinc-50 font-heading uppercase">
            AI Bond Trading System
          </h1>
          <p className="text-sm text-zinc-400 mt-2">
            Intelligent Government Bond & Rate Futures Trading
          </p>
        </div>

        {/* Auth Card */}
        <div className="bg-zinc-900 border border-zinc-800 p-6 rounded-sm">
          {needs2FA ? (
            <>
              {/* 2FA Verification Step */}
              <div className="flex items-center gap-3 mb-6">
                <button
                  onClick={resetTo2FALogin}
                  className="text-zinc-400 hover:text-white transition-colors"
                  data-testid="back-to-login-btn"
                >
                  <ArrowLeft size={18} />
                </button>
                <div className="flex items-center gap-2">
                  <ShieldCheck size={20} className="text-blue-400" />
                  <span className="text-sm font-semibold text-white uppercase tracking-widest">
                    Two-Factor Authentication
                  </span>
                </div>
              </div>

              <p className="text-xs text-zinc-400 mb-4">
                Enter the 6-digit code from your authenticator app, or use a backup code.
              </p>

              {error && (
                <div className="mb-4 p-3 bg-red-950/50 border border-red-900/50 rounded-sm flex items-center gap-2 text-red-400 text-sm">
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <form onSubmit={handle2FASubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="otp" className="text-xs uppercase tracking-widest text-zinc-500">
                    Verification Code
                  </Label>
                  <div className="relative">
                    <ShieldCheck className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                    <Input
                      id="otp"
                      type="text"
                      placeholder="000000"
                      value={otpCode}
                      onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 8))}
                      data-testid="otp-input"
                      className="pl-10 bg-zinc-950 border-zinc-800 rounded-sm text-zinc-50 placeholder:text-zinc-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 font-mono text-lg tracking-[0.3em] text-center"
                      autoFocus
                      required
                    />
                  </div>
                </div>

                <Button
                  type="submit"
                  disabled={loading || otpCode.length < 6}
                  data-testid="verify-2fa-btn"
                  className="w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold py-2.5 rounded-sm transition-colors uppercase tracking-widest text-sm"
                >
                  {loading ? (
                    <span className="flex items-center justify-center gap-2">
                      <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      Verifying...
                    </span>
                  ) : (
                    <span className="flex items-center justify-center gap-2">
                      Verify & Login
                      <ArrowRight className="w-4 h-4" />
                    </span>
                  )}
                </Button>
              </form>

              <p className="text-[10px] text-zinc-600 mt-4 text-center">
                You can also use a backup code instead of the authenticator code
              </p>
            </>
          ) : (
            <>
              {/* Normal Login/Register */}
              <div className="flex mb-6">
                <button
                  onClick={() => setIsLogin(true)}
                  data-testid="login-tab"
                  className={`flex-1 py-2 text-sm font-semibold uppercase tracking-widest border-b-2 transition-colors ${
                    isLogin 
                      ? 'border-blue-500 text-blue-400' 
                      : 'border-zinc-800 text-zinc-500 hover:text-zinc-300'
                  }`}
                >
                  Login
                </button>
                <button
                  onClick={() => setIsLogin(false)}
                  data-testid="register-tab"
                  className={`flex-1 py-2 text-sm font-semibold uppercase tracking-widest border-b-2 transition-colors ${
                    !isLogin 
                      ? 'border-blue-500 text-blue-400' 
                      : 'border-zinc-800 text-zinc-500 hover:text-zinc-300'
                  }`}
                >
                  Register
                </button>
              </div>

              {error && (
                <div className="mb-4 p-3 bg-red-950/50 border border-red-900/50 rounded-sm flex items-center gap-2 text-red-400 text-sm">
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                {!isLogin && (
                  <div className="space-y-2">
                    <Label htmlFor="name" className="text-xs uppercase tracking-widest text-zinc-500">
                      Full Name
                    </Label>
                    <div className="relative">
                      <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                      <Input
                        id="name"
                        type="text"
                        placeholder="John Doe"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        data-testid="name-input"
                        className="pl-10 bg-zinc-950 border-zinc-800 rounded-sm text-zinc-50 placeholder:text-zinc-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 font-mono text-sm"
                      />
                    </div>
                  </div>
                )}

                <div className="space-y-2">
                  <Label htmlFor="email" className="text-xs uppercase tracking-widest text-zinc-500">
                    Email Address
                  </Label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                    <Input
                      id="email"
                      type="email"
                      placeholder="trader@example.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      data-testid="email-input"
                      className="pl-10 bg-zinc-950 border-zinc-800 rounded-sm text-zinc-50 placeholder:text-zinc-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 font-mono text-sm"
                      required
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="password" className="text-xs uppercase tracking-widest text-zinc-500">
                    Password
                  </Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                    <Input
                      id="password"
                      type="password"
                      placeholder="--------"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      data-testid="password-input"
                      className="pl-10 bg-zinc-950 border-zinc-800 rounded-sm text-zinc-50 placeholder:text-zinc-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 font-mono text-sm"
                      required
                    />
                  </div>
                </div>

                <Button
                  type="submit"
                  disabled={loading}
                  data-testid="auth-submit-btn"
                  className="w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold py-2.5 rounded-sm transition-colors uppercase tracking-widest text-sm"
                >
                  {loading ? (
                    <span className="flex items-center justify-center gap-2">
                      <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      Processing...
                    </span>
                  ) : (
                    <span className="flex items-center justify-center gap-2">
                      {isLogin ? 'Access Terminal' : 'Create Account'}
                      <ArrowRight className="w-4 h-4" />
                    </span>
                  )}
                </Button>
              </form>

              <div className="mt-6 pt-4 border-t border-zinc-800 text-center">
                <p className="text-xs text-zinc-500">
                  {isLogin ? "Don't have an account?" : "Already have an account?"}{' '}
                  <button
                    onClick={() => setIsLogin(!isLogin)}
                    className="text-blue-400 hover:text-blue-300 transition-colors"
                  >
                    {isLogin ? 'Register now' : 'Login here'}
                  </button>
                </p>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-zinc-600 mt-6">
          Powered by GPT-5.2 AI Engine - Real-time Market Analysis
        </p>
      </div>
    </div>
  );
};

export default AuthPage;
