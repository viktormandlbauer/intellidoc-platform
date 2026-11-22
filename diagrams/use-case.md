# MVP use cases

The diagram shows the Must user stories from the [requirements](../docs/requirements.md#31-overview) and the [MVP scope](../docs/mvp.md#3-included-must).
Repository permissions are cumulative from Reader to Contributor to Repo Admin.
A Global Admin has Repo Admin permissions in every active repository.

```mermaid
flowchart LR
    operator["Operator"]
    admin["Global Admin"]
    repoAdmin["Repo Admin"]
    contributor["Contributor"]
    reader["Reader"]

    subgraph platform["IntelliDoc Platform"]
        bootstrap(["Bootstrap the first Global Admin (US-1)"])
        login(["Sign in (US-2)"])
        users(["Manage users (US-2)"])
        repositories(["Create a repository (US-3)"])
        rename(["Rename a repository (US-3)"])
        appoint(["Assign or revoke Repo Admin (US-3)"])
        memberships(["Manage repository membership (US-4)"])
        upload(["Upload PDFs and check processing status (US-5)"])
        documents(["List and download documents (US-6)"])
        search(["Search by natural language or exact term (US-7)"])
        scope(["Apply current repository access (US-8)"])
        own(["Deactivate own documents (US-9)"])
        anyDocument(["Deactivate any document in the repository (US-9)"])
        answer(["Ask a question and get an answer with sources (US-13)"])
    end

    operator --- bootstrap
    admin --- users
    admin --- repositories
    admin --- appoint
    repoAdmin --- memberships
    repoAdmin --- anyDocument
    repoAdmin --- rename
    contributor --- upload
    contributor --- own
    reader --- documents
    reader --- search
    reader --- answer
    admin --- login
    repoAdmin --- login
    contributor --- login
    reader --- login
    search -.-> scope
    answer -.-> scope
```
