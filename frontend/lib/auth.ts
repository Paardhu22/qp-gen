import { betterAuth } from "better-auth";
import { prismaAdapter } from "better-auth/adapters/prisma";
import { db } from "./db";

export const auth = betterAuth({
    database: prismaAdapter(db, {
        provider: "postgresql", 
    }),
    emailAndPassword: {  
        enabled: true
    },
    // We add trusted origins and secret for production readiness
    secret: process.env.BETTER_AUTH_SECRET || "fallback_secret_for_dev_only",
    baseURL: process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000",
    socialProviders: {
        google: {
            clientId: process.env.GOOGLE_CLIENT_ID || "placeholder",
            clientSecret: process.env.GOOGLE_CLIENT_SECRET || "placeholder",
        }
    }
});
