# Jarumba Music — Architecture

> **Status note (2026-09-18).**  Sections below that mention a "Rust/Axum
> backend" describe the original plan, which is **superseded** (see
> [ADR 0001](decisions/0001-rust-backend.md)): the implemented backend is a
> **Python/FastAPI** application in `services/api`, using SQLAlchemy +
> Alembic against Supabase PostgreSQL, Supabase Auth (JWT/JWKS, ES256), Redis
> for shared rate limiting, and Jamendo as the only active music provider.
> Implementation status: `/auth/me`, `/music/search`, `/profile`,
> `/favorites`, `/playlists` (+tracks), `/recently-played`, `/health`,
> `/health/db` are **IMPLEMENTED and hardened**; Audiomack support is
> **PLANNED/DEFERRED**; Railway deployment is **PLANNED**.

## 1. Architecture Overview:this is a simple music listening app which from the user to the app then our API which interacts with a music provider and supabase .
# Jarumba Music — Architecture

## 1. Architecture Overview:this is a simple music listening app which from the user to the app then our API which interacts with a music provider and supabase . 

User interacts with the mobile application which is built using flutter and dart.   

app -> api ->  supabse and music provider (for music/metadata)



## 2. System Context:from the user to our andriod app then rust api and supabase to the music provider very simple 

## 3. High-Level Architecture:![alt text](image-1.png)

## 4. Mobile Application:The mobile application will be built with React Native and Expo and will serve as the primary interface for Jarumba Music users. It will provide the user interface for authentication, music discovery, search, playback, playlists, favorites, listening history, and settings. The application will communicate with the Rust/Axum backend through HTTPS APIs for server-side operations and data. The music player will handle playback controls such as play, pause, seek, skip, and queue management. Authorized tracks will be cached locally on the device to support offline playback where permitted by the music provider. Authentication session information and other sensitive local data will be stored using secure device storage. The mobile application will not contain backend secrets or privileged credentials.

## 5. Backend API

The backend will be implemented as a single Rust application using the Axum web framework and Tokio asynchronous runtime. The API will be responsible for handling authenticated requests from the mobile application, business logic, music provider integration, playlist management, likes, listening history, and download permission checks. The backend will communicate with Supabase PostgreSQL for application data and Supabase Auth for authentication verification. The backend will use middleware for authentication, authorization, rate limiting, request tracing, and other cross-cutting concerns. The initial architecture will use a modular monolith rather than multiple microservices because the application is targeting approximately 100 initial users.

## 6. Database

The application will use PostgreSQL through Supabase. The database will store application-specific data rather than the audio catalog itself. The initial data model will include users, playlists, playlist tracks, likes, and listening history. Relationships and constraints will be enforced at the database level where appropriate. Row Level Security (RLS) will be used to restrict access to user-owned data. Database changes will be managed through version-controlled migrations.

## 7. Authentication and Authorization

Supabase Auth will manage user authentication. Google will be the initial authentication provider, with Apple authentication considered for a future release. After authentication, the mobile application will receive a user session and use its access token when communicating with the Rust API. The Rust backend will validate the authenticated user's identity before processing protected requests. Authorization will determine whether the authenticated user is allowed to access or modify a requested resource. Database Row Level Security will provide an additional authorization boundary for user-owned data.

## 8. Music Provider Integration

The Rust backend will communicate with an external music provider through a dedicated provider integration layer. The provider layer will isolate third-party API-specific logic from the rest of the application. The initial provider will be selected based on its licensing terms, API availability, streaming permissions, and support for permitted downloads. The application will only expose music and functionality that are allowed by the provider's terms and the applicable content licenses. Provider credentials and other secrets will remain on trusted server-side infrastructure and will not be embedded in the mobile application.

## 9. Offline Caching

The mobile application will support local caching of authorized audio for offline playback. Before a track is cached for offline use, the application will receive confirmation that the provider permits the intended download or offline behavior. Cached content will be stored locally on the device and managed by the application. The initial implementation will focus on reliable caching, playback, cache management, and handling the absence of network connectivity. The application will not claim to provide unrestricted downloads for content that does not permit them.

## 10. Security Boundaries

The mobile application will be treated as an untrusted client. All security-sensitive decisions will be enforced by the backend and database rather than relying solely on mobile client behavior. Authentication tokens will be stored using secure device storage. Backend secrets, service-role credentials, database credentials, and provider secrets will never be included in the mobile application or committed to source control. The API will validate input, enforce authorization, apply rate limits, use parameterized database queries, and return safe error responses. Communication between the mobile application and backend will use HTTPS.

## 11. Data Flow

A typical authenticated request will follow this flow:

Mobile App
→ Authentication Session
→ Rust/Axum API
→ Authentication Verification
→ Authorization
→ Business Logic
→ PostgreSQL or Music Provider
→ API Response
→ Mobile App

For music search, the mobile application sends a search request to the Rust API. The Rust API communicates with the configured music provider, normalizes the provider response, and returns the required track information to the mobile application.

For user-owned resources such as playlists, the Rust API identifies the authenticated user, verifies authorization, performs the required database operation, and returns the result.

For offline caching, the application checks whether the requested track is permitted for offline use before storing it locally.

## 12. API Communication

The mobile application and backend will communicate through HTTPS using a JSON-based REST API for the MVP. Protected endpoints will require a valid authentication token. The API will use standard HTTP methods and status codes and will return consistent response and error structures. Request validation will occur at the API boundary before business logic is executed. Pagination will be used for endpoints that may return large collections such as search results, playlists, and listening history.

Initial endpoint groups will include:

- Health
- Authentication and current user
- Music search and track information
- Playlists
- Likes
- Listening history
- Download permissions

## 13. Deployment Architecture

The MVP will be designed to operate with minimal infrastructure and cost. The Android application will be distributed as an installable APK during early testing rather than depending on the Google Play Store. The Rust API will run as a single deployable service. Supabase will provide managed authentication and PostgreSQL infrastructure. The music provider will provide the permitted music catalog and associated media access. Docker will be used to provide a reproducible backend development and deployment environment.

## 14. Technology Decisions

The MVP will use the following technologies:

- React Native with Expo for the Android mobile application
- Rust with Axum for the backend API
- Tokio for asynchronous Rust execution
- PostgreSQL through Supabase for application data
- Supabase Auth for authentication
- SQLx for Rust database access
- HTTPS and JSON REST APIs for application communication
- Local device storage for offline caching
- Docker for reproducible backend environments
- GitHub Actions for continuous integration
- Python for the future recommendation system

The initial backend architecture will remain a modular monolith. The system will only be split into separate services when there is a demonstrated engineering requirement to do so.

## 15. Future Extensions

Future versions may introduce personalized music recommendations, machine-learning-based ranking, additional authentication providers, iOS support, artist and creator features, improved offline content management, additional music providers, analytics, and other product capabilities.

These extensions are intentionally outside the initial MVP so that the first release can focus on reliability, security, legal music access, and a good core listening experience.